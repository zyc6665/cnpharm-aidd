import torch
import torch.nn as nn
import dgl
import dgl.function as fn
from torch import Tensor
from typing import Optional


class Extract3DFeatures(nn.Module):
    def __init__(self, node_feats_dim, edge_feats_dim, node_mlp_hidden_dim, edge_mlp_hidden_dim, dropout=0.2,
                 edge_attr_dim=0, update_coors=False, update_feats=True, soft_edge=True,
                 include_rel_coords=False, activation="leaky_relu"):
        super(Extract3DFeatures, self).__init__()
        self.update_coors = update_coors  # 是否更新坐标
        self.update_feats = update_feats  # 是否更新节点特征
        self.soft_edge = soft_edge  # 可选的边权重处理
        self.include_rel_coords = include_rel_coords

        if include_rel_coords:
            edge_feats_dim += 3
        edge_feats_dim += edge_attr_dim
        activation_layer = nn.SiLU() if activation == "silu" else nn.LeakyReLU(negative_slope=0.01)
        # 节点特征的 MLP
        self.node_mlp = nn.Sequential(
            nn.Linear(node_feats_dim + node_mlp_hidden_dim, node_mlp_hidden_dim),
            activation_layer,
            nn.LayerNorm(node_mlp_hidden_dim),  # 添加BatchNorm
            nn.Dropout(dropout),  # 加入 Dropout
            nn.Linear(node_mlp_hidden_dim, node_feats_dim)
        )
        # 边特征的 MLP
        self.edge_mlp = nn.Sequential(
            nn.Linear(node_feats_dim * 2 + edge_feats_dim, edge_mlp_hidden_dim),
            nn.SiLU() if activation == "silu" else nn.LeakyReLU(negative_slope=0.01),
            nn.LayerNorm(edge_mlp_hidden_dim),  # 添加BatchNorm
            nn.Dropout(dropout),  # 加入 Dropout
            nn.Linear(edge_mlp_hidden_dim, edge_mlp_hidden_dim)
        )
        # 坐标的 MLP（用于坐标更新）
        self.coors_mlp = nn.Sequential(
            nn.Linear(edge_mlp_hidden_dim, 1),
            nn.ReLU()

        )
        # 可选的边权重
        if self.soft_edge:
            self.edge_weight = nn.Sequential(
                nn.Linear(edge_mlp_hidden_dim, 1),
                nn.Sigmoid()
            )

        # 可选的节点正则化
        self.node_norm = nn.LayerNorm(node_feats_dim)
        self.coors_norm = CoorsNorm(scale_init=1e-2)

    def forward(self, graph, x, coords, edge_attr=None):
        """
        graph: DGL 图对象
        x: 节点特征 (N, node_feats_dim)
        coords: 节点的 3D 坐标 (N, 3)
        edge_attr: 边特征（如果有的话）
        """
        # 1. 计算相对坐标和欧氏距离
        edge_src, edge_dst = graph.edges()
        rel_coors = coords[edge_src] - coords[edge_dst]  # 相对坐标
        rel_dist = (rel_coors ** 2).sum(dim=-1, keepdim=True)  # 欧氏距离平方
        # 2. 处理边特征
        if edge_attr is not None:
            if edge_attr.dim()==1:
                edge_attr=edge_attr.unsqueeze(1)
            if self.include_rel_coords:
                edge_attr_feats = torch.cat([edge_attr, rel_coors], dim=-1)  # 边特征和相对坐标组合
            else:
                edge_attr_feats = torch.cat([edge_attr, rel_dist], dim=-1)  # 边特征和距离组合
        else:
            edge_attr_feats = rel_coors if self.include_rel_coords else rel_dist

        # 设置边特征
        graph.edata['edge_attr'] = edge_attr_feats
        # 设置节点特征
        graph.ndata['x'] = x
        graph.ndata['coords'] = coords
        # graph=graph.to(device)
        # 3. 执行消息传递
        graph.update_all(self.message_func, self.reduce_func)
        if self.update_coors:
        # 4. 返回更新后的节点特征和坐标
            return graph.ndata['h'], graph.ndata['coords']
        else:
            return graph.ndata['h']

    def message_func(self, edges):
        """
        消息传递函数
        计算每一条边的消息。
        """
        src_feats = edges.src['x']
        dst_feats = edges.dst['x']
        edge_feats = edges.data['edge_attr']
        # 计算边的消息
        m_ij = self.edge_mlp(torch.cat([src_feats, dst_feats, edge_feats], dim=-1))

        # 可选的边权重
        if self.soft_edge:
            m_ij = m_ij * self.edge_weight(m_ij)  # 加权边特征

        return {'msg': m_ij}

    def reduce_func(self, nodes):


        # 聚合邻居的消息
        aggregated_msg = torch.mean(nodes.mailbox['msg'], dim=1)

        # 更新节点特征（如果需要）
        if self.update_feats:
            node_feats = nodes.data['x']
            hidden_feats = self.node_norm(node_feats) if self.node_norm else node_feats
            hidden_out = self.node_mlp(torch.cat([hidden_feats, aggregated_msg], dim=-1))  # 更新后的节点特征
            hidden_out = node_feats + hidden_out  # 残差连接
        else:
            hidden_out = nodes.data['x']

        nodes.data['h'] = hidden_out

        # 更新坐标（如果需要）
        if self.update_coors:
            coors_wij = self.coors_mlp(aggregated_msg)
            rel_coors = nodes.data['coords']
            normed_coors = self.coors_norm(rel_coors)
            coors_out = rel_coors + coors_wij * normed_coors  # 更新后的坐标
        else:
            coors_out = nodes.data['coords']

        nodes.data['coords'] = coors_out

        return nodes.data


class CoorsNorm(nn.Module):
    def __init__(self, eps=1e-8, scale_init=1.):
        super().__init__()
        self.eps = eps
        scale = torch.zeros(1).fill_(scale_init)
        self.scale = nn.Parameter(scale)

    def forward(self, coors):
        norm = coors.norm(dim=-1, keepdim=True)  # 每个元素的范数，欧几里得范数
        normed_coors = coors / norm.clamp(min=self.eps)
        return normed_coors * self.scale
