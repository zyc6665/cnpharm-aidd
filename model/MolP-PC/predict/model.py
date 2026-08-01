import math

from sklearn.metrics import roc_auc_score, mean_squared_error, precision_recall_curve, auc, r2_score,accuracy_score, precision_score, recall_score, f1_score, confusion_matrix, classification_report
import torch
import torch.nn.functional as F
import dgl
import numpy as np
import random
from dgl.readout import sum_nodes,max_nodes,mean_nodes
from dgl.nn.pytorch.conv import RelGraphConv
from torch import nn
import pandas as pd


from dgl.nn import GATConv

import torch.distributed as dist

# from new_3d_feature import get_3D_GAT, GraphGather, flatten
from Extract3DFeature import Extract3DFeatures
from rdkit import Chem
from rdkit.Chem import rdmolops, AllChem
import pubchemfp
from rdkit import RDLogger
RDLogger.DisableLog('rdApp.*')


class WeightAndSum(nn.Module):
    def __init__(self, in_feats, task_num=1, attention=True, return_weight=False):
        super(WeightAndSum, self).__init__()
        self.attention = attention
        self.in_feats = in_feats
        self.task_num = task_num
        self.return_weight = return_weight
        self.atom_weighting_specific = nn.ModuleList([self.atom_weight(self.in_feats) for _ in range(self.task_num)])
        self.shared_weighting = self.atom_weight(self.in_feats)
    def forward(self,feats):
        feat_list = []
        atom_list = []
        # cal specific feats

        for i in range(self.task_num):

            feats_weight=self.atom_weighting_specific[i](feats)
            specific_feats=feats_weight*feats
            feat_list.append(specific_feats)
            atom_list.append(feats_weight)

        feat_data = torch.stack(feat_list)
        # cal shared feats
        # feat_list.append(shared_feats_sum)
        if self.attention:
            if self.return_weight:
                return feat_data, atom_list
            else:
                return feat_data
        else:
            # shared_feats_1 = self.shared_cross_atten(two_feats, one_feats, one_feats)

            feats_weight = self.atom_weighting_specific[i](feats)
            shared_feats = feats_weight * feats
            # shared_feats=self.shared_cross_atten(two_feats, three_feats, three_feats)
            return shared_feats

    def atom_weight(self, in_feats):
        return nn.Sequential(
            nn.Linear(in_feats, 1),
            nn.Sigmoid()
            )



class Attention_fusion(nn.Module):
    def __init__(self, input_dim, dim_k, dim_v,weight_3d=2.0):
        super(Attention_fusion, self).__init__()
        # self.q = nn.Sequential( nn.Linear(input_dim, dim_k), nn.LayerNorm(dim_k), nn.Dropout(0.2), )
        # self.k = nn.Sequential( nn.Linear(input_dim, dim_k), nn.LayerNorm(dim_k), nn.Dropout(0.2), )
        # self.v = nn.Sequential(nn.Linear(input_dim, dim_k), )
        self.q = nn.Sequential(nn.LayerNorm(dim_k), nn.Linear(input_dim, dim_k), nn.LayerNorm(dim_k), nn.Dropout(0.2),)
        self.k = nn.Sequential(nn.LayerNorm(dim_k), nn.Linear(input_dim, dim_k),nn.LayerNorm(dim_k),nn.Dropout(0.2),)
        self.v = nn.Sequential(nn.Linear(input_dim, dim_v),nn.LayerNorm(dim_v), nn.ReLU())
        # self.dropout = nn.Dropout(0.2)
        # self.norm = nn.LayerNorm(input_dim)  # LayerNorm 归一化
        # self.out_proj = nn.Linear(dim_v, input_dim)  # 线性变换到输入维度
        self._norm_fact = 1 / math.sqrt(dim_k)
        self.bn = nn.BatchNorm1d(3)

    def forward(self, x):
        Q = self.q(x)
        K = self.k(x)
        V = self.v(x)
        # score = torch.bmm(Q, K.permute(0, 2, 1)) * self._norm_fact
        temperature = 2  # 可以调整
        score= torch.bmm(Q, K.permute(0, 2, 1)) * self._norm_fact
        atten = nn.Softmax(-1)(score/temperature)
        # atten = self.dropout(atten)
        output = torch.bmm(atten, V)
        # out = output.view(x.shape[0], -1)
        # print(output.size(),out.size())
        # 6. 融合输出 (求平均池化，得到最终的分子特征)
        # output = self.out_proj(output) + x  # 残差连接
        # output = self.norm(output)  # 归一化
        out = torch.mean(output, dim=1)  # (B, D)
        return out


class FeatureFusionWithGated(nn.Module):
    def __init__(self, embed_dim):
        super(FeatureFusionWithGated, self).__init__()
        self.gate_fc = nn.Linear(embed_dim * 3, 3)  # 输出3个门控值
        # 全连接层，用于融合后的特征降维
        self.fc = nn.Linear(embed_dim, embed_dim)

    def forward(self, feat_1d, feat_2d, feat_3d):
        feats = torch.cat([feat_1d, feat_2d, feat_3d], dim=-1)  # (B, embed_dim * 3)

        # 计算门控值
        gates = torch.sigmoid(self.gate_fc(feats))  # (B, 3)

        # 使用门控值对特征进行加权求和
        fused_feat = (
                gates[:, 0].unsqueeze(-1) * feat_1d +  # (B, embed_dim)
                gates[:, 1].unsqueeze(-1) * feat_2d +  # (B, embed_dim)
                gates[:, 2].unsqueeze(-1) * feat_3d  # (B, embed_dim)
        )  # (B, embed_dim)
        # 通过全连接层降维
        output = self.fc(fused_feat)  # (B, embed_dim)

        return output




class MLPBinaryClassifier(nn.Module):
    def __init__(self, in_feats, hidden_feats, n_tasks, dropout=0.):
        super(MLPBinaryClassifier, self).__init__()

        self.predict = nn.Sequential(
            nn.Dropout(dropout),
            nn.Linear(in_feats, hidden_feats),
            nn.ReLU(),
            nn.BatchNorm1d(hidden_feats),
            nn.Linear(hidden_feats, n_tasks)
        )

    def forward(self, h):
        return self.predict(h)


class RGCNLayer(nn.Module):
    def __init__(self, in_feats, out_feats, num_rels=64*21, activation=F.relu, loop=False,
                 residual=True, batchnorm=True, rgcn_drop_out=0.5, residual_bias=True):
        super(RGCNLayer, self).__init__()

        self.activation = activation
        self.graph_conv_layer = RelGraphConv(in_feats, out_feats, num_rels=num_rels, regularizer='basis',
                                               num_bases=None, bias=True, activation=activation,
                                               self_loop=loop, dropout=rgcn_drop_out)
        self.residual = residual
        if residual:
            self.res_connection = nn.Linear(in_feats, out_feats, bias=residual_bias)

        self.bn = batchnorm
        if batchnorm:
            self.bn_layer = nn.BatchNorm1d(out_feats)

    def forward(self, bg, node_feats, etype, norm=None):
        new_feats = self.graph_conv_layer(bg, node_feats, etype, norm)
        if self.residual:
            res_feats = self.activation(self.res_connection(node_feats))
            new_feats = new_feats + res_feats
        if self.bn:
            new_feats = self.bn_layer(new_feats)
        return new_feats
class GAT(nn.Module):
    def __init__(self,
                 n_layers, #层数
                 in_feats, #输入特征维度
                 n_hidden, #隐层特征维度
                 n_classes, #类别数
                 heads, #多头注意力的数量
                 activation, #激活函数
                 in_drop, #输入特征的Dropout比例
                 at_drop, #注意力特征的Dropout比例
                 negative_slope, #注意力计算中Leaky ReLU的a值
                 use_norms=False,
                 ):
        super(GAT, self).__init__()
        self.num_layers = n_layers
        self.activation = activation
        self.use_norms = use_norms

        self.gat_layers = nn.ModuleList()
        self.norms = nn.ModuleList()

        self.gat_layers.append(GATConv(in_feats, n_hidden, heads[0],
                                       in_drop, at_drop, negative_slope, activation=self.activation, allow_zero_in_degree=True))

        for l in range(1, n_layers):
            self.gat_layers.append(GATConv(n_hidden * heads[l-1], n_hidden, heads[l],
                                           in_drop, at_drop, negative_slope, activation=self.activation, allow_zero_in_degree=True))

        self.gat_layers.append(GATConv(n_hidden * heads[-2], n_classes, heads[-1],
                                       in_drop, at_drop, negative_slope, activation=None, allow_zero_in_degree=True))
        if self.use_norms:
            for l in range(n_layers):
                self.norms.append(nn.LayerNorm(n_hidden * heads[l]))

    def forward(self, g, inputs):
        h = inputs
        for l in range(self.num_layers):
            h = self.gat_layers[l](g, h).flatten(1)
            if self.use_norms:
                h = self.norms[l](h)
        logits = self.gat_layers[-1](g, h).mean(1)
        return logits

class FPN(nn.Module):
    def __init__(self, hidden_feats ,fp_type="mixed",fp_changebit = None ):
        super(FPN, self).__init__()
        self.fp_2_dim = 512
        self.hidden_dim = hidden_feats
        self.fp_type = fp_type
        if self.fp_type == 'mixed':
            self.fp_dim = 1489
        else:
            self.fp_dim = 1024
        self.fp_changebit = fp_changebit
        self.fc1 = nn.Linear(self.fp_dim, self.fp_2_dim)
        self.act_func = nn.ReLU()
        self.fc2 = nn.Linear(self.fp_2_dim, self.hidden_dim)
        self.dropout = nn.Dropout(0.5)
        self.batch_norm1 = nn.BatchNorm1d(self.fp_2_dim)  # BatchNorm

    def forward(self, smiles,device):

        fp_list = []
        for i, one in enumerate(smiles):
            fp = []
            mol = Chem.MolFromSmiles(one)
            mol = Chem.RemoveHs(mol)  # 显式去除氢原子
            if self.fp_type == 'mixed':
                fp_maccs = AllChem.GetMACCSKeysFingerprint(mol)
                fp_phaErGfp = AllChem.GetErGFingerprint(mol, fuzzIncrement=0.3, maxPath=21, minPath=1)
                fp_pubcfp = pubchemfp.GetPubChemFPs(mol)
                fp.extend(fp_maccs)
                fp.extend(fp_phaErGfp)
                fp.extend(fp_pubcfp)
            else:
                fp_morgan = AllChem.GetMorganFingerprintAsBitVect(mol, 2, nBits=1024)
                fp.extend(fp_morgan)
            fp_list.append(fp)
        if self.fp_changebit is not None and self.fp_changebit != 0:
            fp_list = np.array(fp_list)
            fp_list[:, self.fp_changebit - 1] = np.ones(fp_list[:, self.fp_changebit - 1].shape)
            fp_list.tolist()
        fp_list = torch.tensor(np.array(fp_list)).float().to(device)
        fpn_out = self.fc1(fp_list)
        fpn_out = self.batch_norm1(fpn_out)
        fpn_out = self.dropout(fpn_out)
        fpn_out = self.act_func(fpn_out)
        fpn_out = self.fc2(fpn_out)
        del fp_list
        torch.cuda.empty_cache()
        return fpn_out
class MGA(nn.Module):
    def __init__(self, in_feats, hidden_feats, n_tasks,n_layers, return_mol_embedding=False, return_weight=False,
                 classifier_hidden_feats=256, dropout=0.2, pooling="sum",ftype="mixed",loop=False,
                 task_output_dim=3, admet_backbone=False):
        super(MGA, self).__init__()
        self.in_feats = in_feats
        self.gnn_layers = nn.ModuleList()
        self.out_feats =  hidden_feats[-2]
        self.task_num = n_tasks
        self.task_output_dim = task_output_dim
        self.admet_backbone = admet_backbone
        self.return_weight = return_weight
        # 返回的是task_num个TFP列表
        self.return_mol_embedding = return_mol_embedding
        # 1D
        self.fpn = FPN(hidden_feats=hidden_feats[-3], fp_type=ftype)
        #2D
        for i in range(len(hidden_feats)):
            residual = not (self.admet_backbone and i == len(hidden_feats) - 1)
            self.gnn_layers.append(RGCNLayer(in_feats, hidden_feats[i], loop=loop, rgcn_drop_out=0.2,
                                             residual=residual,
                                             residual_bias=not self.admet_backbone))
            in_feats=hidden_feats[i]
        gat_at_drop = 0.5 if self.admet_backbone else dropout
        self.GATattention = GAT(n_layers=n_layers, in_feats=self.in_feats, n_hidden=self.out_feats,n_classes=self.out_feats,
                                heads=([n_layers] * n_layers) + [1], activation=F.elu, in_drop=dropout, at_drop=gat_at_drop,
                                negative_slope=0.2, use_norms=self.admet_backbone)
        #3D
        self.extra_3d = Extract3DFeatures(node_feats_dim=self.in_feats, edge_feats_dim=1,
                                          node_mlp_hidden_dim=hidden_feats[-3],
                                          edge_mlp_hidden_dim=hidden_feats[-3],
                                          edge_attr_dim=0 if self.admet_backbone else 1,
                                          dropout=0.3 if self.admet_backbone else dropout,
                                          include_rel_coords=self.admet_backbone,
                                          activation="silu" if self.admet_backbone else "leaky_relu")
        get_3d_in_feats = self.in_feats if self.admet_backbone else self.in_feats * 2
        self.get_3d_gat = GAT(n_layers=n_layers, in_feats=get_3d_in_feats, n_hidden=hidden_feats[-3], n_classes=hidden_feats[-3],
                              heads=([n_layers] * n_layers) + [1], activation=F.elu, in_drop=dropout, at_drop=gat_at_drop,
                              negative_slope=0.2, use_norms=self.admet_backbone)
        #特征融合
        # self.fusion=FeatureFusionWithGated(hidden_feats[-3])
        self.atten_fusion = Attention_fusion(hidden_feats[-3], hidden_feats[-3], hidden_feats[-3])
        self.weighted_sum_readout = WeightAndSum(hidden_feats[-3], self.task_num, return_weight=self.return_weight)
        #任务权重
        # 全连接层
        head_dropout = 0.3 if self.admet_backbone else dropout
        self.fc_layers1 = nn.ModuleList(
            [self.fc_layer(head_dropout, hidden_feats[-3], classifier_hidden_feats) for _ in range(self.task_num)])
        self.fc_layers2 = nn.ModuleList(
            [self.fc_layer(head_dropout, classifier_hidden_feats, classifier_hidden_feats) for _ in range(self.task_num)])
        self.fc_layers3 = nn.ModuleList(
            [self.fc_layer(head_dropout, classifier_hidden_feats, classifier_hidden_feats) for _ in range(self.task_num)])
        # 输出层
        self.output_layer1 = nn.ModuleList(
                [self.output_layer(classifier_hidden_feats, self.task_output_dim) for _ in range(self.task_num)])


    def forward(self,smiles,pos_g, bg, node_feats, etype, device='cpu',norm=None):
        #3D
        pos_node_feats=pos_g.ndata['atom'].float()
        mask = pos_g.ndata['mask'].float().unsqueeze(1)
        updated_nodes=self.extra_3d(pos_g,pos_node_feats,pos_g.ndata['pos'].float(),edge_attr=pos_g.edata['etype'].float())
        if self.admet_backbone:
            X = updated_nodes
        else:
            X=torch.cat(([pos_node_feats,updated_nodes]),dim=-1)
        new_feats=self.get_3d_gat(pos_g,X)*mask
        three_feats=self.flatten(pos_g, new_feats)
        #2D
        node_feats_fc = node_feats
        for gnn in self.gnn_layers:
            node_feats_fc = gnn(bg, node_feats_fc, etype, norm)

        atten_feats = self.GATattention(bg, node_feats)
        atten_feats = torch.cat([node_feats_fc, atten_feats], dim=-1)
        two_feats = self.flatten(bg, atten_feats)
        #1D
        fp_feats=self.fpn(smiles,device)
        #fusion
        feats_out = torch.stack([fp_feats, two_feats, three_feats], dim=1)
        feats = self.atten_fusion(feats_out)
        del fp_feats,two_feats,three_feats,atten_feats,node_feats,node_feats_fc,new_feats,mask,pos_node_feats
        torch.cuda.empty_cache()
        feats_list=self.weighted_sum_readout(feats)
        for i in range(self.task_num):
            mol_feats = feats_list[i]#取TFP
            mol_feats = torch.cat([mol_feats], dim=1)
            # mol_feats = self.linear1(mol_feats)
            # mol_feats = self.linear2(mol_feats)

            h1 = self.fc_layers1[i](mol_feats)#三层全连接层
            h2 = self.fc_layers2[i](h1)
            h3 = self.fc_layers3[i](h2)
            predict = self.output_layer1[i](h3)
            if i == 0:
                prediction_all = predict
            else:
                prediction_all = torch.cat([prediction_all, predict], dim=1)#将tensor拼接，合成一个总体的预测结果
        # generate toxicity fingerprints
        if self.return_mol_embedding:
            return "return_mol_embedding"
            # return feats_list[0]
        else:
            # generate atom weight and atom feats
            if self.return_weight:
                return "return_weight"
                # return prediction_all, atom_weight_list, node_feats
            # just generate prediction
            return prediction_all
    def flatten(self,bg,feats,pooling="sum"):
        with bg.local_scope():
            bg.ndata['h'] = feats  # 节点特征
            if pooling=='sum':
                specific_feats = sum_nodes(bg,'h')
            elif pooling=="max":
                specific_feats = max_nodes(bg, 'h')
            elif pooling=="avg":
                specific_feats = mean_nodes(bg, 'h')
            return specific_feats


    def fc_layer(self, dropout, in_feats, hidden_feats):
        return nn.Sequential(
                nn.Dropout(dropout),
                nn.Linear(in_feats, hidden_feats),
                nn.ReLU(),
                nn.BatchNorm1d(hidden_feats)
                )

    def output_layer(self, hidden_feats, out_feats):
        return nn.Sequential(
                nn.Linear(hidden_feats, out_feats)
                )


def set_random_seed(seed=10):
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.backends.cudnn.benchmark = False
    torch.backends.cudnn.deterministic = True
    if torch.cuda.is_available():
        torch.cuda.manual_seed(seed)


def pos_weight(train_set, classification_num):
    smiles, pos_g, graphs, labels, mask = map(list, zip(*train_set))
    labels = np.array(labels)
    task_pos_weight_list = []

    num_pos = 0
    num_impos = 0
    num_twpos=0
    num=len(labels)
    for i in labels:
        if i==2:
            num_twpos=num_twpos+1
        if i == 1:
            num_pos = num_pos + 1
        if i == 0:
            num_impos = num_impos + 1
    weight = [num/num_impos, num/num_pos, num/num_twpos]
    weight = torch.tensor(weight)
    weight= weight / (weight.mean())

    return weight


class Meter(object):
    """Track and summarize model performance on a dataset for
    (multi-label) binary classification.跟踪和汇总模型的性能，多标签，二分类"""
    def __init__(self):
        self.mask = []
        self.y_pred = []
        self.y_true = []

    def update(self, y_pred, y_true, mask):
        """Update for the result of an iteration
        Parameters更新迭代结果参数
        ----------
        y_pred : float32 tensor
            Predicted molecule labels with shape (B, T),预测分子标签
            B for batch size and T for the number of tasks
        y_true : float32 tensor
            Ground truth molecule labels with shape (B, T)，真实分子标签
        mask : float32 tensor
            Mask for indicating the existence of ground，掩饰真实标签的存在
            truth labels with shape (B, T)
        """
        self.y_pred.append(y_pred.detach().cpu())#detach()阻止反向传播，变量仍在GPU上，cpu()将变量保存在cpu中
        self.y_true.append(y_true.detach().cpu())
        self.mask.append(mask.detach().cpu())

    def roc_auc_score(self):#计算AUC的值
        """Compute roc-auc score for each task.
        Returns
        -------
        list of float
            roc-auc score for all tasks
        """
        mask = torch.cat(self.mask, dim=0)
        y_pred = torch.cat(self.y_pred, dim=0)
        y_true = torch.cat(self.y_true, dim=0)
        # y_pred = torch.argmax(y_pred, dim=0).numpy()
        # y_true = torch.argmax(y_true, dim=0).numpy()
        y_true = y_true.cpu().numpy()
        y_pred = y_pred.cpu().numpy()
        n_tasks = 1
        scores = []
        scores.append(round(roc_auc_score(y_true, y_pred, multi_class="ovo",
              average="macro"), 4))
        return scores

    def return_pred_true(self):
        """Compute roc-auc score for each task.
        Returns
        -------
        list of float
            roc-auc score for all tasks
        """
        mask = torch.cat(self.mask, dim=0)
        y_pred = torch.cat(self.y_pred, dim=0)
        y_true = torch.cat(self.y_true, dim=0)
        # Todo: support categorical classes
        # This assumes binary case only
        y_pred = torch.sigmoid(y_pred)
        n_tasks = y_true.shape[1]
        scores = []
        return y_pred, y_true

    def l1_loss(self, reduction):
        """Compute l1 loss for each task.
        Returns
        -------
        list of float
            l1 loss for all tasks
        reduction : str
            * 'mean': average the metric over all labeled data points for each task
            * 'sum': sum the metric over all labeled data points for each task
        """
        mask = torch.cat(self.mask, dim=0)
        y_pred = torch.cat(self.y_pred, dim=0)
        y_true = torch.cat(self.y_true, dim=0)
        n_tasks = y_true.shape[1]
        scores = []
        for task in range(n_tasks):
            task_w = mask[:, task]
            task_y_true = y_true[:, task][task_w != 0].numpy()
            task_y_pred = y_pred[:, task][task_w != 0].numpy()
            scores.append(F.l1_loss(task_y_true, task_y_pred, reduction=reduction).item())#所有目标值和模型输出之间的绝对值的平均值，回归任务
        return scores

    def rmse(self):
        """Compute RMSE for each task.
        Returns
        -------
        list of float
            rmse for all tasks
        """
        mask = torch.cat(self.mask, dim=0)
        y_pred = torch.cat(self.y_pred, dim=0)
        y_true = torch.cat(self.y_true, dim=0)
        n_data, n_tasks = y_true.shape
        scores = []
        for task in range(n_tasks):
            task_w = mask[:, task]
            task_y_true = y_true[:, task][task_w != 0].numpy()
            task_y_pred = y_pred[:, task][task_w != 0].numpy()
            scores.append(np.sqrt(F.mse_loss(task_y_pred, task_y_true).cpu().item()))#均方根误差，所有目标值与预测值的插值平方和的平均值的平方根
        return scores

    def mae(self):
        """Compute MAE for each task.
        Returns
        -------
        list of float
            mae for all tasks
        """
        mask = torch.cat(self.mask, dim=0)
        y_pred = torch.cat(self.y_pred, dim=0)
        y_true = torch.cat(self.y_true, dim=0)
        n_data, n_tasks = y_true.shape
        scores = []
        for task in range(n_tasks):
            task_w = mask[:, task]
            task_y_true = y_true[:, task][task_w != 0].numpy()
            task_y_pred = y_pred[:, task][task_w != 0].numpy()
            scores.append(mean_squared_error(task_y_true, task_y_pred))#均方误差，所有目标值与预测值的插值平方和的平均值
        return scores

    def r2(self):
        """Compute R2 for each task.
        Returns
        -------
        list of float
            r2 for all tasks
        """
        mask = torch.cat(self.mask, dim=0)
        y_pred = torch.cat(self.y_pred, dim=0)
        y_true = torch.cat(self.y_true, dim=0)
        n_data, n_tasks = y_true.shape
        scores = []
        for task in range(n_tasks):
            task_w = mask[:, task]
            task_y_true = y_true[:, task][task_w != 0].numpy()
            task_y_pred = y_pred[:, task][task_w != 0].numpy()
            scores.append(round(r2_score(task_y_true, task_y_pred), 4))#决定系数，1-（所有目标值与预测值之间的差值的平方和/目标值与平均值的插值平方和）
        return scores

    def roc_precision_recall_score(self):
        """Compute AUC_PRC for each task.
        Returns
        -------
        list of float
            AUC_PRC for all tasks
        """
        mask = torch.cat(self.mask, dim=0)
        y_pred = torch.cat(self.y_pred, dim=0)
        y_true = torch.cat(self.y_true, dim=0)
        # Todo: support categorical classes
        # This assumes binary case only
        y_pred = torch.sigmoid(y_pred)
        n_tasks = y_true.shape[1]
        scores = []
        for task in range(n_tasks):
            task_w = mask[:, task]
            task_y_true = y_true[:, task][task_w != 0].numpy()
            task_y_pred = y_pred[:, task][task_w != 0].numpy()
            precision, recall, _thresholds = precision_recall_curve(task_y_true, task_y_pred)
            #计算精度召回曲线，precision查准率-预测的正例中真正的正例有多少，recall查全率-真正的正例中有多少被准确预测，_thresholds阈值，大于阈值为正样本，小于为负样本
            scores.append(auc(recall, precision))
        return scores

    def accuracy(self):
        """Compute accuracy for each task."""
        mask = torch.cat(self.mask, dim=0)
        y_pred = torch.cat(self.y_pred, dim=0)
        y_true = torch.cat(self.y_true, dim=0)
        y_pred = torch.argmax(y_pred, dim=1).numpy()
        y_true = torch.argmax(y_true, dim=1).numpy()
        n_tasks = 1
        scores = []
        scores.append(accuracy_score(y_true, y_pred))
        return scores

    def precision(self, average='macro'):
        """Compute precision for each task."""
        mask = torch.cat(self.mask, dim=0)
        y_pred = torch.cat(self.y_pred, dim=0)
        y_true = torch.cat(self.y_true, dim=0)
        y_pred = torch.argmax(y_pred, dim=1).numpy()
        y_true = torch.argmax(y_true, dim=1).numpy()
        n_tasks = 1
        scores = []
        scores.append(precision_score(y_true, y_pred, average=average))
        return scores

    def recall(self, average='macro'):
        """Compute recall for each task."""
        mask = torch.cat(self.mask, dim=0)
        y_pred = torch.cat(self.y_pred, dim=0)
        y_true = torch.cat(self.y_true, dim=0)
        y_pred = torch.argmax(y_pred, dim=1).numpy()
        y_true = torch.argmax(y_true, dim=1).numpy()
        n_tasks = 1
        scores = []
        scores.append(recall_score(y_true, y_pred, average=average))
        return scores

    def f1(self, average='macro'):
        """Compute F1 score for each task."""
        mask = torch.cat(self.mask, dim=0)
        y_pred = torch.cat(self.y_pred, dim=0)
        y_true = torch.cat(self.y_true, dim=0)
        y_pred = torch.argmax(y_pred, dim=1).numpy()
        y_true = torch.argmax(y_true, dim=1).numpy()
        n_tasks = 1
        scores = []

        scores.append(f1_score(y_true, y_pred, average=average))
        return scores
    def compute_metric(self, metric_name, reduction='mean'):
        """Compute metric for each task.
        Parameters
        ----------
        metric_name : str
            Name for the metric to compute.
        reduction : str
            Only comes into effect when the metric_name is l1_loss.
            * 'mean': average the metric over all labeled data points for each task
            * 'sum': sum the metric over all labeled data points for each task
        Returns
        -------
        list of float
            Metric value for each task
        """
        assert metric_name in ['roc_auc', 'l1', 'rmse', 'mae', 'roc_prc', 'r2', 'return_pred_true','acc','f1','precision','recall'], \
            'Expect metric name to be "roc_auc", "l1" or "rmse", "mae", "roc_prc", "r2", "return_pred_true", got {}'.format(metric_name)
        assert reduction in ['mean', 'sum']#断言为true时往下进行
        if metric_name == 'roc_auc':
            return self.roc_auc_score()
        if metric_name == 'l1':
            return self.l1_loss(reduction)
        if metric_name == 'rmse':
            return self.rmse()
        if metric_name == 'mae':
            return self.mae()
        if metric_name == 'roc_prc':
            return self.roc_precision_recall_score()
        if metric_name == 'r2':
            return self.r2()
        if metric_name == 'return_pred_true':
            return self.return_pred_true()
        if metric_name == 'acc':
            return self.accuracy()
        if metric_name == 'f1':
            return self.f1()
        if metric_name == 'precision':
            return self.precision()
        if metric_name == 'recall':
            return self.recall()


def collate_molgraphs(data):
    smiles, pos_g, graphs, labels, mask  = map(list, zip(*data))
    bg = dgl.batch(graphs)
    bg.set_n_initializer(dgl.init.zero_initializer)
    bg.set_e_initializer(dgl.init.zero_initializer)
    pos_bg = dgl.batch(pos_g)
    pos_bg.set_n_initializer(dgl.init.zero_initializer)
    pos_bg.set_e_initializer(dgl.init.zero_initializer)
    # labels = torch.tensor(np.array(labels))
    # mask = torch.tensor(mask)

    # adjms=torch.tensor(adjms)
    # features=torch.tensor(features)

    return smiles, pos_bg, bg,
def run_a_train_epoch_heterogeneous(args, epoch, model, data_loader, loss_criterion_c, loss_criterion_r, optimizer, task_weight=None):
    model.train()
    train_meter_c = Meter()
    train_meter_r = Meter()
    if task_weight is not None:
        task_weight = task_weight.float().to(args['device'])
    loss_all=0


    for batch_id, batch_data in enumerate(data_loader):
        smiles, pos_g, bg, labels, mask = batch_data
        mask = mask.float().to(args['device'])
        pos_g=pos_g.to(args['device'])
        bg = bg.to(args['device'])
        atom_feats = bg.ndata.pop(args['atom_data_field']).float().to(args['device'])
        bond_feats = bg.edata.pop(args['bond_data_field']).long().to(args['device'])
        logits = model(smiles,pos_g, bg, atom_feats, bond_feats,device=args['device'],norm=None)
        labels=F.one_hot(torch.tensor(labels, dtype=torch.long),3).squeeze(1)
        labels = labels.type_as(logits).to(args['device'])
        # calculate loss according to different task class
        if args['task_class'] == 'classification_regression':
            # split classification and regression
            logits_c = logits[:,:args['classification_num']]
            labels_c = labels[:,:args['classification_num']]
            mask_c = mask[:,:args['classification_num']]

            logits_r = logits[:,args['classification_num']:]
            labels_r = labels[:,args['classification_num']:]
            mask_r = mask[:,args['classification_num']:]
            # chose loss function according to task_weight
            if task_weight is None:
                loss = (loss_criterion_c(logits_c, labels_c)*(mask_c != 0).float()).mean() \
                       + (loss_criterion_r(logits_r, labels_r)*(mask_r != 0).float()).mean()
            else:
                task_weight_c = task_weight[:args['classification_num']]
                task_weight_r = task_weight[args['classification_num']:]
                loss = (torch.mean(loss_criterion_c(logits_c, labels_c)*(mask_c != 0).float(), dim=0)*task_weight_c).mean() \
                       + (torch.mean(loss_criterion_r(logits_r, labels_r)*(mask_r != 0).float(), dim=0)*task_weight_r).mean()
            loss_all = loss_all + loss
            # 梯度裁剪
            torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
            train_meter_c.update(logits_c, labels_c, mask_c)
            train_meter_r.update(logits_r, labels_r, mask_r)
            del bg, mask, labels, atom_feats, bond_feats, loss, logits_c, logits_r, labels_c, labels_r, mask_c, mask_r,pos_g
            torch.cuda.empty_cache()
        elif args['task_class'] == 'classification':
            # chose loss function according to task_weight
            if task_weight is None:
                loss = (loss_criterion_c(logits, labels)*(mask != 0).float()).mean()
            else:
                loss = (torch.mean(loss_criterion_c(logits, labels) * (mask != 0).float(),dim=0)*task_weight).mean()
            loss_all = loss_all + loss
            # 梯度裁剪
            torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
            train_meter_c.update(logits, labels, mask)
            del bg, mask, labels, atom_feats, bond_feats, loss,  logits,pos_g
            torch.cuda.empty_cache()
        else:
            # chose loss function according to task_weight
            if task_weight is None:
                loss = (loss_criterion_r(logits, labels)*(mask != 0).float()).mean()
            else:
                loss = (torch.mean(loss_criterion_r(logits, labels) * (mask != 0).float(), dim=0)*task_weight).mean()
            loss_all = loss_all + loss
            # 梯度裁剪
            torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
            train_meter_r.update(logits, labels, mask)
            del bg, mask, labels, atom_feats, bond_feats, loss,  logits,pos_g
            torch.cuda.empty_cache()
    if args['task_class'] == 'classification_regression':
        train_score = np.mean(train_meter_c.compute_metric(args['classification_metric_name']) +
                              train_meter_r.compute_metric(args['regression_metric_name']))
        print('epoch {:d}/{:d}, training {} {:.4f} ,loss {:.4f}'.format(
            epoch + 1, args['num_epochs'], 'r2+auc', train_score,loss_all/len(data_loader)))
    elif args['task_class'] == 'classification':
        train_score = np.mean(train_meter_c.compute_metric(args['classification_metric_name']))
        print('epoch {:d}/{:d}, training {} {:.4f} ,loss {:.4f}'.format(
            epoch + 1, args['num_epochs'], args['classification_metric_name'], train_score,loss_all/len(data_loader)))
    else:
        train_score = np.mean(train_meter_r.compute_metric(args['regression_metric_name']))
        print('epoch {:d}/{:d}, training {} {:.4f} ,loss {:.4f}'.format(
            epoch + 1, args['num_epochs'], args['regression_metric_name'], train_score,loss_all/len(data_loader)))


def run_an_eval_epoch_heterogeneous(args, model, data_loader):
    model.eval()
    eval_meter_c = Meter()
    eval_meter_r = Meter()
    smilesls=[]
    predsls=[]
    with torch.no_grad():
        for batch_id, batch_data in enumerate(data_loader):
            smiles, pos_g, bg, = batch_data
            # mask = mask.float().to(args['device'])
            pos_g = pos_g.to(args['device'])
            bg = bg.to(args['device'])
            atom_feats = bg.ndata.pop(args['atom_data_field']).float().to(args['device'])
            bond_feats = bg.edata.pop(args['bond_data_field']).long().to(args['device'])
            logits = model(smiles, pos_g, bg, atom_feats, bond_feats, device=args['device'], norm=None)
            smilesls.append(smiles)
            predsls.append(logits)
        return smilesls,predsls
        #     labels = F.one_hot(torch.tensor(labels, dtype=torch.long), 3).squeeze(1)
        #     labels = labels.type_as(logits).to(args['device'])
        #     # print(labels.shape,logits.shape)
        #     if args['task_class'] == 'classification_regression':
        #         # split classification and regression
        #         logits_c = logits[:, :args['classification_num']]
        #         labels_c = labels[:, :args['classification_num']]
        #         mask_c = mask[:, :args['classification_num']]
        #         logits_r = logits[:, args['classification_num']:]
        #         labels_r = labels[:, args['classification_num']:]
        #         mask_r = mask[:, args['classification_num']:]
        #         # Mask non-existing labels
        #         eval_meter_c.update(logits_c, labels_c, mask_c)
        #         eval_meter_r.update(logits_r, labels_r, mask_r)
        #         del smiles, bg,  mask, labels, atom_feats, bond_feats, logits_c, logits_r, labels_c, labels_r, mask_c, mask_r,pos_g
        #         torch.cuda.empty_cache()
        #     elif args['task_class'] == 'classification':
        #         # Mask non-existing labels
        #         eval_meter_c.update(logits, labels, mask)
        #         del smiles, bg,  mask, labels, atom_feats, bond_feats, logits,pos_g
        #         torch.cuda.empty_cache()
        #     else:
        #         # Mask non-existing labels
        #         eval_meter_r.update(logits, labels, mask)
        #         del smiles, bg,  mask, labels, atom_feats, bond_feats, logits,pos_g
        #         torch.cuda.empty_cache()
        #
        # if args['task_class'] == 'classification_regression':
        #     return eval_meter_c.compute_metric(args['classification_metric_name']) + \
        #            eval_meter_r.compute_metric(args['regression_metric_name'])
        # elif args['task_class'] == 'classification':
        #     return eval_meter_c.compute_metric(args['classification_metric_name'])
        # else:
        #     return eval_meter_r.compute_metric(args['regression_metric_name'])




def generate_chemical_environment(args, model, data_loader):
    model.eval()
    atom_list_all = []
    with torch.no_grad():
        for batch_id, batch_data in enumerate(data_loader):
            print("batch: {}/{}".format(batch_id + 1, len(data_loader)))
            smiles, bg, labels, mask, coords = batch_data
            print(bg.ndata[args['atom_data_field']][1])
            bg = bg.to(args['device'])
            atom_feats = bg.ndata.pop(args['atom_data_field']).float().to(args['device'])
            bond_feats = bg.edata.pop(args['bond_data_field']).long().to(args['device'])
            logits, atom_weight_list = model(bg, atom_feats, bond_feats, norm=None)
            print('after training:', bg.ndata['h'][1])


def generate_mol_feats(args, model, data_loader, dataset_output_path):
    model.eval()
    with torch.no_grad():
        for batch_id, batch_data in enumerate(data_loader):
            smiles, bg, labels, mask, coords = batch_data
            bg = bg.to(args['device'])
            atom_feats = bg.ndata.pop(args['atom_data_field']).float().to(args['device'])
            bond_feats = bg.edata.pop(args['bond_data_field']).long().to(args['device'])
            feats = model(bg, atom_feats, bond_feats, norm=None).numpy().tolist()
            feats_name = ['graph-feature' + str(i+1) for i in range(64)]
            data = pd.DataFrame(feats, columns=feats_name)
            data['smiles'] = smiles
            data['labels'] = labels.squeeze().numpy().tolist()
    data.to_csv(dataset_output_path, index=None)


class EarlyStopping(object):
    def __init__(self, pretrained_model='Null_early_stop.pth', mode='higher', patience=10, filename=None, task_name="None"):
        if filename is None:
            task_name = task_name
            filename ='../ADMET_model/{}_early_stop_atten_acc.pth'.format(task_name)

        assert mode in ['higher', 'lower']#断言，为true时执行
        self.mode = mode
        if self.mode == 'higher':
            self._check = self._check_higher
        else:
            self._check = self._check_lower

        self.patience = patience#50
        self.counter = 0
        self.filename = filename
        self.best_score = None
        self.early_stop = False
        self.pretrained_model = pretrained_model

    def _check_higher(self, score, prev_best_score):
        return (score > prev_best_score)

    def _check_lower(self, score, prev_best_score):
        return (score < prev_best_score)

    def step(self, score, model):
        if self.best_score is None:
            self.best_score = score
            self.save_checkpoint(model)
        elif self._check(score, self.best_score):
            self.best_score = score
            self.save_checkpoint(model)
            self.counter = 0
        else:
            self.counter += 1
            print(
                'EarlyStopping counter: {} out of {}'.format(self.counter, self.patience))
            if self.counter >= self.patience:
                self.early_stop = True
        return self.early_stop

    def nosave_step(self, score):
        if self.best_score is None:
            self.best_score = score
        elif self._check(score, self.best_score):
            self.best_score = score
            self.counter = 0
        else:
            self.counter += 1
            print(
                'EarlyStopping counter: {} out of {}'.format(self.counter, self.patience))
            if self.counter >= self.patience:
                self.early_stop = True
        return self.early_stop

    def save_checkpoint(self, model):
        '''Saves model when the metric on the validation set gets improved.在验证集上的指标得到改进时保存模型'''
        # torch.save({'model_state_dict': model.state_dict()}, self.filename)
        torch.save(model, self.filename)
        # print(self.filename)

    def load_checkpoint(self, model):
    # def load_checkpoint(self):
        '''Load model saved with early stopping.加载用早停保存的模型'''
        # model.load_state_dict(torch.load(self.filename)['model_state_dict'])
        model.load_state_dict(torch.load(self.filename, map_location=torch.device('cpu')).state_dict())
        # torch.load(self.filename, map_location=torch.device('cpu'))
        #map_location映射到cpu上跑，torch.load用于加载torch.save()保存的文件，load_state_dict()加载模型参数


    def load_pretrained_model(self, model):
        pretrained_parameters = [param for param in model.parameters()]
        if torch.cuda.is_available():  # 查看cuda是否可用
            pretrained_model = torch.load("../ADMET_model/atten_fusion/" + self.pretrained_model,map_location=torch.device('cpu'))
        else:  # 如果不可用，映射到cpu上
            pretrained_model = torch.load("../ADMET_model/atten_fusion/" + self.pretrained_model,map_location=torch.device('cpu'))
        model_dict = model.state_dict()#state_dict()用于存放各个层需要学习的权重和偏置
        pretrained_dict = {k: v for k, v in pretrained_model['model_state_dict'].items() if k in pretrained_parameters}
        # pretrained_dict={k: v for k, v in pretrained_model.state_dict().items() if k in pretrained_parameters}
        model_dict.update(pretrained_dict)#更新已有的键的值，存入没有的键值对
        model.load_state_dict(pretrained_dict, strict=False)#加载模型参数

    def load_model_attention(self, model):
        # pretrained_parameters = ['gnn_layers.0.graph_conv_layer.weight',
        #                          'gnn_layers.0.graph_conv_layer.h_bias',
        #                          'gnn_layers.0.graph_conv_layer.loop_weight',
        #                          'gnn_layers.0.res_connection.weight',
        #                          'gnn_layers.0.res_connection.bias',
        #                          'gnn_layers.0.bn_layer.weight',
        #                          'gnn_layers.0.bn_layer.bias',
        #                          'gnn_layers.0.bn_layer.running_mean',
        #                          'gnn_layers.0.bn_layer.running_var',
        #                          'gnn_layers.0.bn_layer.num_batches_tracked',
        #                          'gnn_layers.1.graph_conv_layer.weight',
        #                          'gnn_layers.1.graph_conv_layer.h_bias',
        #                          'gnn_layers.1.graph_conv_layer.loop_weight',
        #                          'gnn_layers.1.res_connection.weight',
        #                          'gnn_layers.1.res_connection.bias',
        #                          'gnn_layers.1.bn_layer.weight',
        #                          'gnn_layers.1.bn_layer.bias',
        #                          'gnn_layers.1.bn_layer.running_mean',
        #                          'gnn_layers.1.bn_layer.running_var',
        #                          'gnn_layers.1.bn_layer.num_batches_tracked',
        #                          'weighted_sum_readout.atom_weighting_specific.0.0.weight',
        #                          'weighted_sum_readout.atom_weighting_specific.0.0.bias',
        #                          'weighted_sum_readout.atom_weighting_specific.1.0.weight',
        #                          'weighted_sum_readout.atom_weighting_specific.1.0.bias',
        #                          'weighted_sum_readout.atom_weighting_specific.2.0.weight',
        #                          'weighted_sum_readout.atom_weighting_specific.2.0.bias',
        #                          'weighted_sum_readout.atom_weighting_specific.3.0.weight',
        #                          'weighted_sum_readout.atom_weighting_specific.3.0.bias',
        #                          'weighted_sum_readout.atom_weighting_specific.4.0.weight',
        #                          'weighted_sum_readout.atom_weighting_specific.4.0.bias',
        #                          'weighted_sum_readout.atom_weighting_specific.5.0.weight',
        #                          'weighted_sum_readout.atom_weighting_specific.5.0.bias',
        #                          'weighted_sum_readout.atom_weighting_specific.6.0.weight',
        #                          'weighted_sum_readout.atom_weighting_specific.6.0.bias',
        #                          'weighted_sum_readout.atom_weighting_specific.7.0.weight',
        #                          'weighted_sum_readout.atom_weighting_specific.7.0.bias',
        #                          'weighted_sum_readout.atom_weighting_specific.8.0.weight',
        #                          'weighted_sum_readout.atom_weighting_specific.8.0.bias',
        #                          'weighted_sum_readout.atom_weighting_specific.9.0.weight',
        #                          'weighted_sum_readout.atom_weighting_specific.9.0.bias',
        #                          'weighted_sum_readout.atom_weighting_specific.10.0.weight',
        #                          'weighted_sum_readout.atom_weighting_specific.10.0.bias',
        #                          'weighted_sum_readout.atom_weighting_specific.11.0.weight',
        #                          'weighted_sum_readout.atom_weighting_specific.11.0.bias',
        #                          'weighted_sum_readout.atom_weighting_specific.12.0.weight',
        #                          'weighted_sum_readout.atom_weighting_specific.12.0.bias',
        #                          'weighted_sum_readout.atom_weighting_specific.13.0.weight',
        #                          'weighted_sum_readout.atom_weighting_specific.13.0.bias',
        #                          'weighted_sum_readout.atom_weighting_specific.14.0.weight',
        #                          'weighted_sum_readout.atom_weighting_specific.14.0.bias',
        #                          'weighted_sum_readout.atom_weighting_specific.15.0.weight',
        #                          'weighted_sum_readout.atom_weighting_specific.15.0.bias',
        #                          'weighted_sum_readout.atom_weighting_specific.16.0.weight',
        #                          'weighted_sum_readout.atom_weighting_specific.16.0.bias',
        #                          'weighted_sum_readout.atom_weighting_specific.17.0.weight',
        #                          'weighted_sum_readout.atom_weighting_specific.17.0.bias',
        #                          'weighted_sum_readout.atom_weighting_specific.18.0.weight',
        #                          'weighted_sum_readout.atom_weighting_specific.18.0.bias',
        #                          'weighted_sum_readout.atom_weighting_specific.19.0.weight',
        #                          'weighted_sum_readout.atom_weighting_specific.19.0.bias',
        #                          'weighted_sum_readout.atom_weighting_specific.20.0.weight',
        #                          'weighted_sum_readout.atom_weighting_specific.20.0.bias',
        #                          'weighted_sum_readout.atom_weighting_specific.21.0.weight',
        #                          'weighted_sum_readout.atom_weighting_specific.21.0.bias',
        #                          'weighted_sum_readout.atom_weighting_specific.22.0.weight',
        #                          'weighted_sum_readout.atom_weighting_specific.22.0.bias',
        #                          'weighted_sum_readout.atom_weighting_specific.23.0.weight',
        #                          'weighted_sum_readout.atom_weighting_specific.23.0.bias',
        #                          'weighted_sum_readout.atom_weighting_specific.24.0.weight',
        #                          'weighted_sum_readout.atom_weighting_specific.24.0.bias',
        #                          'weighted_sum_readout.atom_weighting_specific.25.0.weight',
        #                          'weighted_sum_readout.atom_weighting_specific.25.0.bias',
        #                          'weighted_sum_readout.atom_weighting_specific.26.0.weight',
        #                          'weighted_sum_readout.atom_weighting_specific.26.0.bias',
        #                          'weighted_sum_readout.atom_weighting_specific.27.0.weight',
        #                          'weighted_sum_readout.atom_weighting_specific.27.0.bias',
        #                          'weighted_sum_readout.atom_weighting_specific.28.0.weight',
        #                          'weighted_sum_readout.atom_weighting_specific.28.0.bias',
        #                          'weighted_sum_readout.atom_weighting_specific.29.0.weight',
        #                          'weighted_sum_readout.atom_weighting_specific.29.0.bias',
        #                          'weighted_sum_readout.atom_weighting_specific.30.0.weight',
        #                          'weighted_sum_readout.atom_weighting_specific.30.0.bias',
        #                          'weighted_sum_readout.shared_weighting.0.weight',
        #                          'weighted_sum_readout.shared_weighting.0.bias',
        #                          ]
        pretrained_parameters = [
            "gnn_layers.0.graph_conv_layer.h_bias",
            "gnn_layers.0.graph_conv_layer.loop_weight",
            "gnn_layers.0.graph_conv_layer.linear_r.W",
            "gnn_layers.0.graph_conv_layer.linear_r.coeff",
            "gnn_layers.0.res_connection.weight",
            "gnn_layers.0.res_connection.bias",
            "gnn_layers.0.bn_layer.weight",
            "gnn_layers.0.bn_layer.bias",
            "gnn_layers.0.bn_layer.running_mean",
            "gnn_layers.0.bn_layer.running_var",
            "gnn_layers.0.bn_layer.num_batches_tracked",
            "gnn_layers.1.graph_conv_layer.h_bias",
            "gnn_layers.1.graph_conv_layer.loop_weight",
            "gnn_layers.1.graph_conv_layer.linear_r.W",
            "gnn_layers.1.graph_conv_layer.linear_r.coeff",
            "gnn_layers.1.res_connection.weight",
            "gnn_layers.1.res_connection.bias",
            "gnn_layers.1.bn_layer.weight",
            "gnn_layers.1.bn_layer.bias",
            "gnn_layers.1.bn_layer.running_mean",
            "gnn_layers.1.bn_layer.running_var",
            "gnn_layers.1.bn_layer.num_batches_tracked",
            "gnn_layers.2.graph_conv_layer.h_bias",
            "gnn_layers.2.graph_conv_layer.loop_weight",
            "gnn_layers.2.graph_conv_layer.linear_r.W",
            "gnn_layers.2.graph_conv_layer.linear_r.coeff",
            "gnn_layers.2.res_connection.weight",
            "gnn_layers.2.res_connection.bias",
            "gnn_layers.2.bn_layer.weight",
            "gnn_layers.2.bn_layer.bias",
            "gnn_layers.2.bn_layer.running_mean",
            "gnn_layers.2.bn_layer.running_var",
            "gnn_layers.2.bn_layer.num_batches_tracked",
            "gnn_layers.3.graph_conv_layer.h_bias",
            "gnn_layers.3.graph_conv_layer.loop_weight",
            "gnn_layers.3.graph_conv_layer.linear_r.W",
            "gnn_layers.3.graph_conv_layer.linear_r.coeff",
            "gnn_layers.3.res_connection.weight",
            "gnn_layers.3.res_connection.bias",
            "gnn_layers.3.bn_layer.weight",
            "gnn_layers.3.bn_layer.bias",
            "gnn_layers.3.bn_layer.running_mean",
            "gnn_layers.3.bn_layer.running_var",
            "gnn_layers.3.bn_layer.num_batches_tracked",
            "fpn.fc1.weight",
            "fpn.fc1.bias",
            "fpn.fc2.weight",
            "fpn.fc2.bias",
            "fpn.batch_norm1.weight",
            "fpn.batch_norm1.bias",
            "fpn.batch_norm1.running_mean",
            "fpn.batch_norm1.running_var",
            "fpn.batch_norm1.num_batches_tracked",
            "GATattention.gat_layers.0.attn_l",
            "GATattention.gat_layers.0.attn_r",
            "GATattention.gat_layers.0.bias",
            "GATattention.gat_layers.0.fc.weight",
            "GATattention.gat_layers.1.attn_l",
            "GATattention.gat_layers.1.attn_r",
            "GATattention.gat_layers.1.bias",
            "GATattention.gat_layers.1.fc.weight",
            "GATattention.gat_layers.2.attn_l",
            "GATattention.gat_layers.2.attn_r",
            "GATattention.gat_layers.2.bias",
            "GATattention.gat_layers.2.fc.weight",
            "GATattention.gat_layers.3.attn_l",
            "GATattention.gat_layers.3.attn_r",
            "GATattention.gat_layers.3.bias",
            "GATattention.gat_layers.3.fc.weight",
            "extra_3d.node_mlp.0.weight",
            "extra_3d.node_mlp.0.bias",
            "extra_3d.node_mlp.2.weight",
            "extra_3d.node_mlp.2.bias",
            "extra_3d.node_mlp.4.weight",
            "extra_3d.node_mlp.4.bias",
            "extra_3d.edge_mlp.0.weight",
            "extra_3d.edge_mlp.0.bias",
            "extra_3d.edge_mlp.2.weight",
            "extra_3d.edge_mlp.2.bias",
            "extra_3d.edge_mlp.4.weight",
            "extra_3d.edge_mlp.4.bias",
            "extra_3d.coors_mlp.0.weight",
            "extra_3d.coors_mlp.0.bias",
            "extra_3d.edge_weight.0.weight",
            "extra_3d.edge_weight.0.bias",
            "extra_3d.node_norm.weight",
            "extra_3d.node_norm.bias",
            "extra_3d.coors_norm.scale",
            "get_3d_gat.gat_layers.0.attn_l",
            "get_3d_gat.gat_layers.0.attn_r",
            "get_3d_gat.gat_layers.0.bias",
            "get_3d_gat.gat_layers.0.fc.weight",
            "get_3d_gat.gat_layers.1.attn_l",
            "get_3d_gat.gat_layers.1.attn_r",
            "get_3d_gat.gat_layers.1.bias",
            "get_3d_gat.gat_layers.1.fc.weight",
            "get_3d_gat.gat_layers.2.attn_l",
            "get_3d_gat.gat_layers.2.attn_r",
            "get_3d_gat.gat_layers.2.bias",
            "get_3d_gat.gat_layers.2.fc.weight",
            "get_3d_gat.gat_layers.3.attn_l",
            "get_3d_gat.gat_layers.3.attn_r",
            "get_3d_gat.gat_layers.3.bias",
            "get_3d_gat.gat_layers.3.fc.weight",
            "fusion.gate_fc.weight",
            "fusion.gate_fc.bias",
            "fusion.fc.weight",
            "fusion.fc.bias",
            "weighted_sum_readout.atom_weighting_specific.0.0.weight",
            "weighted_sum_readout.atom_weighting_specific.0.0.bias",
            "weighted_sum_readout.atom_weighting_specific.1.0.weight",
            "weighted_sum_readout.atom_weighting_specific.1.0.bias",
            "weighted_sum_readout.atom_weighting_specific.2.0.weight",
            "weighted_sum_readout.atom_weighting_specific.2.0.bias",
            "weighted_sum_readout.atom_weighting_specific.3.0.weight",
            "weighted_sum_readout.atom_weighting_specific.3.0.bias",
            "weighted_sum_readout.atom_weighting_specific.4.0.weight",
            "weighted_sum_readout.atom_weighting_specific.4.0.bias",
            "weighted_sum_readout.atom_weighting_specific.5.0.weight",
            "weighted_sum_readout.atom_weighting_specific.5.0.bias",
            "weighted_sum_readout.atom_weighting_specific.6.0.weight",
            "weighted_sum_readout.atom_weighting_specific.6.0.bias",
            "weighted_sum_readout.atom_weighting_specific.7.0.weight",
            "weighted_sum_readout.atom_weighting_specific.7.0.bias",
            "weighted_sum_readout.atom_weighting_specific.8.0.weight",
            "weighted_sum_readout.atom_weighting_specific.8.0.bias",
            "weighted_sum_readout.atom_weighting_specific.9.0.weight",
            "weighted_sum_readout.atom_weighting_specific.9.0.bias",
            "weighted_sum_readout.shared_weighting.0.weight",
            "weighted_sum_readout.shared_weighting.0.bias",
        ]
        if torch.cuda.is_available():
            pretrained_model = torch.load('../ADMET_model/' + self.pretrained_model)
        else:
            pretrained_model = torch.load('../ADMET_model/' + self.pretrained_model, map_location=torch.device('cpu'))
        model_dict = model.state_dict()
        # pretrained_dict = {k: v for k, v in pretrained_model['model_state_dict'].items() if k in pretrained_parameters}
        pretrained_dict = {k: v for k, v in pretrained_model.state_dict().items() if k in pretrained_parameters}
        model_dict.update(pretrained_dict)
        model.load_state_dict(pretrained_dict, strict=False)
