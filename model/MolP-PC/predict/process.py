import os
import pickle
import sys
import pandas as pd
import numpy as np
import torch
from dgl import DGLGraph

from rdkit import Chem
from rdkit.Chem.MolStandardize import rdMolStandardize

sys.path.append("..")
from build_dataset import multi_task_build_dataset  # 假设该函数可处理无标签数据
device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')

def is_valid_smiles(smiles):
    """检查SMILES是否有效"""
    try:
        mol = Chem.MolFromSmiles(smiles)
        return mol is not None
    except Exception:
        return False


def standardize_smiles(smiles):
    """标准化SMILES"""
    try:
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            return None
        mol = rdMolStandardize.Cleanup(mol)  # 清洗分子
        return Chem.MolToSmiles(mol, canonical=True)  # 生成规范SMILES
    except Exception:
        return None


def standardize_mol(df):
    """过滤并标准化分子数据"""
    # 保留有效SMILES
    df_combined = df[df['SMILES'].apply(is_valid_smiles)].copy()
    # 标准化SMILES
    df_combined['SMILES'] = df_combined['SMILES'].apply(standardize_smiles)
    # 移除标准化失败的样本
    df = df_combined.dropna(subset=['SMILES'])
    return df


def process_smiles(data_origin):
    """处理输入数据，生成测试集（无标签）"""
    # 1. 标记所有样本为测试集
    data_origin['group'] = 'test'  # 全部划分为测试集
    smiles_name = 'SMILES'

    # 2. 填充空值（避免后续处理报错）
    data_origin = data_origin.fillna(123456)

    # 3. 构造空标签和mask（因输入无标签）
    # 假设任务为单分类，标签列名可自定义（实际无意义，仅为兼容格式）
    labels_list = [x for x in data_origin.columns if x not in ['SMILES', 'group']]  # 读的是标签列名（‘Hepatotoxicity’）

    # 4. 生成数据集（通过multi_task_build_dataset构造图数据）
    # 注意：若该函数强制要求标签存在，需修改其内部逻辑（允许标签为空）
    data_set_gnn = multi_task_build_dataset(
        dataset_smiles=data_origin,
        labels_list=labels_list,
        smiles_name=smiles_name
    )

    # 5. 解析数据集（提取SMILES和图数据，忽略标签和mask）
    smiles, graphs, _, _, _ = map(list, zip(*data_set_gnn))

    # 6. 构造测试集（无标签、无mask）
    test_set = load_graph_for_test(smiles, graphs)
    return test_set


def load_graph_for_test(smiles, graphs):
    """为测试集处理图数据（统一节点数、构造空标签和mask）"""
    all_smiles = np.array(smiles)
    all_graphs = np.array(graphs)

    # 1. 计算最大节点数（用于统一图大小）
    if len(all_graphs) == 0:
        raise ValueError("无有效图数据，请检查输入SMILES")
    max_node_count = max([g.num_nodes() for g in all_graphs])

    # 2. 统一所有图的节点数（填充或截断）
    pos_g_list = []
    for g in all_graphs:
        # 创建新图用于存储处理后的节点特征和坐标
        pos_g = DGLGraph()
        # 提取原始图的节点特征和坐标（根据实际字段调整）
        features = g.ndata.get('atom', torch.zeros(g.num_nodes(), 40))  # 默认为40维特征
        pos = g.ndata.get('pos', torch.zeros(g.num_nodes(), 3))  # 默认为3维坐标
        N = g.num_nodes()

        # 构造节点掩码（1表示真实节点，0表示填充节点）
        node_mask = torch.zeros(max_node_count)
        node_mask[:N] = 1

        # 填充/截断特征和坐标至最大节点数
        if N < max_node_count:
            # 填充零
            padding_size = max_node_count - N
            features_matrix = torch.cat([features, torch.zeros(padding_size, features.shape[1])], dim=0)
            pos_matrix = torch.cat([pos, torch.zeros(padding_size, pos.shape[1])], dim=0)
        else:
            # 截断
            features_matrix = features[:max_node_count]
            pos_matrix = pos[:max_node_count]

        # 更新新图的节点特征和坐标
        pos_g.add_nodes(max_node_count)
        pos_g.ndata['atom'] = features_matrix.float()
        pos_g.ndata['pos'] = pos_matrix.float()
        pos_g.ndata['mask'] = node_mask.float()  # 节点掩码
        # 复制边信息
        pos_g.add_edges(g.edges()[0], g.edges()[1])
        pos_g.edata["etype"] = g.edata.get("normal", torch.zeros(g.num_edges(), 1)).float()

        pos_g_list.append(pos_g)

    # 3. 构造空标签和mask（适配原有数据格式）
    empty_labels = torch.full((len(all_smiles), 1), 123456.0, dtype=torch.float64)  # 空标签
    empty_mask = torch.zeros((len(all_smiles), 1), dtype=torch.float64)  # 空mask

    # 4. 组装测试集（格式：[SMILES, pos_g, graph, 空标签, 空mask]）
    test_set = []
    for i in range(len(all_smiles)):
        test_sample = [
            all_smiles[i],
            pos_g_list[i],
            all_graphs[i],
            empty_labels[i],
            empty_mask[i]
        ]
        test_set.append(test_sample)

    print(f"测试集构造完成，共{len(test_set)}个样本")
    return test_set


def save_test_set(test_set, save_path):
    """保存测试集（支持复杂对象：DGL图、张量等）"""
    # 创建保存目录
    save_dir = os.path.dirname(save_path)
    if save_dir and not os.path.exists(save_dir):
        os.makedirs(save_dir, exist_ok=True)

    # 用pickle保存（兼容DGL图、torch张量）
    try:
        with open(save_path, 'wb') as f:
            pickle.dump(test_set, f, protocol=pickle.HIGHEST_PROTOCOL)
        print.info(f"测试集已保存至：{save_path}")
        return True
    except Exception as e:
        print(f"保存测试集失败：{str(e)}")
        return False


def load_test_set(load_path):
    """加载保存的测试集"""
    if not os.path.exists(load_path):
        raise FileNotFoundError(f"测试集文件不存在：{load_path}")
    try:
        with open(load_path, 'rb') as f:
            test_set = pickle.load(f)
        print(f"成功加载测试集：{load_path}，共{len(test_set)}个样本")
        return test_set
    except Exception as e:
        print(f"加载测试集失败：{str(e)}")
        raise
# # 使用示例
if __name__ == '__main__':
    # 假设输入CSV包含"SMILES"列（无标签）
    input_df = pd.read_csv("cb_data_fine.csv")  # 替换为你的输入文件
    # 标准化处理
    input_df = standardize_mol(input_df)
    # 生成测试集
    test_set = process_smiles(input_df)
    save_test_set(test_set,"cb1_data_fine.pkl")
    # 后续可用于模型预测（test_set中的每个样本包含图数据）