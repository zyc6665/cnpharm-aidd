import os

import pandas as pd
import numpy as np
from rdkit import Chem
from rdkit.Chem import AllChem, rdmolops , MolFromSmiles
import torch
from dgl import DGLGraph
from sklearn.model_selection import train_test_split
import re
from dgl.data.graph_serialize import save_graphs, load_graphs


def split_dataset_according_index(dataset, train_index, val_index, test_index, data_type='np'):
    if data_type == 'pd':
        return pd.DataFrame(dataset[train_index]), pd.DataFrame(dataset[val_index]), pd.DataFrame(dataset[test_index])
    if data_type == 'np':
        return dataset[train_index], dataset[val_index], dataset[test_index]

def one_of_k_encoding(x, allowable_set):  # 提取原子的连接数量
    if x not in allowable_set:
        if 'other' in allowable_set:
            x = 'other'
        else:
            raise Exception("input {0} not in allowable set{1}:".format(x, allowable_set))
    return [x == s for s in allowable_set]


def one_of_k_encoding_unk(x, allowable_set):  # 整理原子元素，将列表外的元素定为other
    """Maps inputs not in the allowable set to the last element."""
    if x not in allowable_set:
        x = allowable_set[-1]
    return [x == s for s in allowable_set]


def atom_features(atom):
    atom_type = one_of_k_encoding(atom.GetSymbol(),
                                  ['B', 'C', 'N', 'O', 'F', 'Si', 'P', 'S', 'Cl', 'As', 'Se', 'Br', 'Te', 'I', 'At',
                                   'other']) + \
                one_of_k_encoding(atom.GetDegree(), [0, 1, 2, 3, 4, 5, 6]) + \
                [atom.GetFormalCharge(), atom.GetNumRadicalElectrons()] + \
                one_of_k_encoding_unk(atom.GetHybridization(),
                                      [Chem.rdchem.HybridizationType.SP, Chem.rdchem.HybridizationType.SP2,
                                       Chem.rdchem.HybridizationType.SP3, Chem.rdchem.HybridizationType.SP3D,
                                       Chem.rdchem.HybridizationType.SP3D2, 'other']) + \
                [atom.GetIsAromatic()] + one_of_k_encoding_unk(atom.GetTotalNumHs(), [0, 1, 2, 3, 4])
    try:
        atom_type = atom_type + one_of_k_encoding_unk(
            atom.GetProp('_CIPCode'),  # 获取'_CIPCode'属性 GetProp() 是R型还是S型
            ['R', 'S']) + [atom.HasProp('_ChiralityPossible')]  # 判断'_ChiralityPossible' 是否存在，手性
    except:
        atom_type = atom_type + [False, False] + [atom.HasProp('_ChiralityPossible')]
    atom_type = np.array(atom_type)
    atom_type = atom_type.astype(int)
    return atom_type


def one_of_k_atompair_encoding(x, allowable_set):
    for atompair in allowable_set:
        if x in atompair:
            x = atompair
            break
        else:
            if atompair == allowable_set[-1]:
                x = allowable_set[-1]
            else:
                continue
    return [x == s for s in allowable_set]


def etype_features(bond, use_chirality=True, atompair=True):
    bt = bond.GetBondType()  # 获取键的类型
    bond_feats_1 = [
        bt == Chem.rdchem.BondType.SINGLE, bt == Chem.rdchem.BondType.DOUBLE,
        bt == Chem.rdchem.BondType.TRIPLE, bt == Chem.rdchem.BondType.AROMATIC,
    ]  # 类似[true,false,false,false]
    for i, m in enumerate(bond_feats_1):
        if m == True:
            a = i

    bond_feats_2 = bond.GetIsConjugated()  # 是否是共轭键
    if bond_feats_2 == True:
        b = 1
    else:
        b = 0

    bond_feats_3 = bond.IsInRing  # 是否在环中
    if bond_feats_3 == True:
        c = 1
    else:
        c = 0

    index = a * 1 + b * 4 + c * 8
    if use_chirality:
        bond_feats_4 = one_of_k_encoding_unk(
            str(bond.GetStereo()),  # 双键立体化学
            ["STEREONONE", "STEREOANY", "STEREOZ", "STEREOE"])  # Z顺 E反
        for i, m in enumerate(bond_feats_4):
            if m == True:
                d = i
        index = index + d * 16
    if atompair == True:
        atom_pair_str = bond.GetBeginAtom().GetSymbol() + bond.GetEndAtom().GetSymbol()  # 双键两端的原子
        bond_feats_5 = one_of_k_atompair_encoding(
            atom_pair_str, [['CC'], ['CN', 'NC'], ['ON', 'NO'], ['CO', 'OC'], ['CS', 'SC'],
                            ['SO', 'OS'], ['NN'], ['SN', 'NS'], ['CCl', 'ClC'], ['CF', 'FC'],
                            ['CBr', 'BrC'], ['others']]
        )
        for i, m in enumerate(bond_feats_5):
            if m == True:
                e = i
        index = index + e * 64
    return index  # 键的转换为一个值


def construct_RGCN_bigraph_from_smiles(smiles):
    try:
        g = DGLGraph()
        # Add nodes
        mol = MolFromSmiles(smiles)  # 保存化学分子
        if mol is None:
            raise ValueError(f"Invalid SMILES string: {smiles}")

        num_atoms = mol.GetNumAtoms()  # 提取原子数


        # num_atoms = mol.GetNumAtoms()#提取原子数
        g.add_nodes(num_atoms)  # 在图中生成与上述数量相同的节点

        atoms_feature_all = []
        for atom_index, atom in enumerate(mol.GetAtoms()):  # mol.GetAtoms()提取每一个原子，都保存为atom对象，返回一个所有原子atom对象组成的列表
            atom_feature = atom_features(atom).tolist()  # 将矩阵转换为列表,全部转化为0/1
            atoms_feature_all.append(atom_feature)  # 每行代表不同原子特征(n,40)
        g.ndata["atom"] = torch.tensor(atoms_feature_all)  # 生成新的张量,并添加到图中，作为节点的特征

        # Add edges
        src_list = []
        dst_list = []
        etype_feature_all = []
        num_bonds = mol.GetNumBonds()  # 获取键的数量
        for i in range(num_bonds):
            bond = mol.GetBondWithIdx(i)  # 根据索引获取键
            etype_feature = etype_features(bond)  # 将键转换为数值
            u = bond.GetBeginAtomIdx()  # 键两端原子的索引
            v = bond.GetEndAtomIdx()
            src_list.extend([u, v])  # extend()在列表末尾一次性追加另一个序列中的多个值（用新列表扩展原来的列表）
            dst_list.extend([v, u])
            etype_feature_all.append(etype_feature)  # 添加俩次??
            etype_feature_all.append(etype_feature)

        g.add_edges(src_list, dst_list)  # 一个键被加入了俩次，俩个双向边表示一个无向图??
        normal_all = []
        for i in etype_feature_all:
            normal = etype_feature_all.count(i) / len(etype_feature_all)  # 统计每个元素出现的次数的比率
            normal = round(normal, 1)  # round() 方法返回浮点数x的四舍五入值。 返回一位小数点后值
            normal_all.append(normal)

        g.edata["etype"] = torch.tensor(etype_feature_all)
        g.edata["normal"] = torch.tensor(normal_all)

        coord = get_smiles_coord(smiles)
        g.ndata['pos']=coord

        return g
    except Exception as e:
        raise ValueError(f"{smiles} failed to transform: {e}")


def build_mask(labels_list, mask_value=100):
    mask = []
    for i in labels_list:
        if i == mask_value:
            mask.append(0)
        else:
            mask.append(1)

    return mask
# def get_smiles_coord(smile):
#     mol = Chem.MolFromSmiles(smile)
#     num_atoms = mol.GetNumAtoms()
#     # posn_tensor=np.zeros((smilen,smilen,3))
#     coords_tensor = torch.zeros((num_atoms, 3), dtype=torch.float32)
#
#     try:
#         mol_3d = Chem.AddHs(mol)  # 添加氢原子
#         # AllChem.EmbedMolecule(mol_3d, randomSeed=1)#生成3D结构，可以考虑进行能量最小化优化
#         # 生成多个构象
#         success = AllChem.EmbedMultipleConfs(mol_3d, maxAttempts=10, randomSeed=12345)
#         if not success:
#             raise ValueError("Failed to generate 3D conformers.")
#         # 优化所有构象并计算能量
#         AllChem.UFFOptimizeMolecule(mol_3d, maxIters=100)  # UFF is faster than MMFF
#
#         conf = mol_3d.GetConformer()
#         print(conf)
#         for i in range(num_atoms):
#             pos = conf.GetAtomPosition(i)
#             coords_tensor[i, :] = torch.tensor([pos.x, pos.y, pos.z], dtype=torch.float32)
#         return coords_tensor
#     except Exception as e:
#         raise ValueError(f"Error generating 3D coordinates for SMILES '{smile}': {e}")
def get_smiles_coord(smile):
    """
    为SMILES生成唯一、可复现的3D坐标（基于能量最低构象）
    Args:
        smile: 输入的SMILES字符串
    Returns:
        coords_tensor: 形状为(num_atoms, 3)的torch张量，对应原分子（不含氢）的原子3D坐标
    Raises:
        ValueError: 无法生成3D构象时抛出
    """
    # -------------------------- 1. 固定全局随机种子（核心：确保可复现） --------------------------
    np.random.seed(12345)  # rdkit底层依赖numpy随机数
    torch.manual_seed(12345)
    # -------------------------- 2. 解析SMILES并验证 --------------------------
    mol = Chem.MolFromSmiles(smile)
    if mol is None:
        raise ValueError(f"Invalid SMILES: {smile}")
    num_atoms = mol.GetNumAtoms()  # 原分子（不含氢）的原子数
    if num_atoms == 0:
        raise ValueError(f"SMILES has no atoms: {smile}")

    # -------------------------- 3. 生成3D构象（多构象+能量筛选） --------------------------
    try:
        # 添加氢原子（用于3D构象生成，最终会剔除氢的坐标）
        mol_3d = Chem.AddHs(mol)
        # 生成多个构象（增加尝试次数确保成功）
        conf_ids = AllChem.EmbedMultipleConfs(
            mol_3d,
            numConfs=10,  # 生成10个构象用于筛选
            maxAttempts=100,  # 增加尝试次数，提高生成成功率
            randomSeed=12345,  # 固定构象生成种子
            pruneRmsThresh=0.5  # 过滤RMSD<0.5的重复构象，减少冗余
        )
        if len(conf_ids) == 0:
            raise ValueError("Failed to generate any 3D conformers")

        # -------------------------- 4. 优化所有构象并计算能量（选能量最低的） --------------------------
        # 优化每个构象的结构（UFF力场，固定参数确保唯一）
        for conf_id in conf_ids:
            AllChem.UFFOptimizeMolecule(
                mol_3d,
                confId=conf_id,
                maxIters=200,  # 固定迭代次数
                vdwThresh=10.0  # 固定范德华作用阈值
            )

        # 计算每个构象的UFF能量，选择能量最低的（最稳定，唯一）
        conf_energies = []
        for conf_id in conf_ids:
            energy = AllChem.UFFGetMoleculeForceField(
                mol_3d,
                confId=conf_id
            ).CalcEnergy()
            conf_energies.append((conf_id, energy))

        # 选能量最低的构象（核心：确保唯一选择）
        best_conf_id = min(conf_energies, key=lambda x: x[1])[0]
        best_conf = mol_3d.GetConformer(best_conf_id)

        # -------------------------- 5. 提取原分子（不含氢）的坐标 --------------------------
        # 映射：加氢后的原子索引 → 原分子（不含氢）的原子索引
        # 过滤掉添加的氢原子，只保留原分子的原子坐标
        coords_tensor = torch.zeros((num_atoms, 3), dtype=torch.float32)
        original_atom_indices = [atom.GetIdx() for atom in mol_3d.GetAtoms() if not atom.GetAtomicNum() == 1]

        if len(original_atom_indices) != num_atoms:
            raise ValueError("Mismatch in atom count after removing H")

        for i, idx in enumerate(original_atom_indices):
            pos = best_conf.GetAtomPosition(idx)
            coords_tensor[i, :] = torch.tensor([pos.x, pos.y, pos.z], dtype=torch.float32)

        return coords_tensor

    except Exception as e:
        raise ValueError(f"Error generating unique 3D coordinates for SMILES '{smile}': {e}")


# import torch.nn.functional as F
def multi_task_build_dataset(dataset_smiles, labels_list, smiles_name):
    dataset_gnn = []
    failed_molecule = []
    labels = dataset_smiles[labels_list] # 读的是标签数据,将所有数据读出来


    split_index = dataset_smiles['group'] # 每一行的数据类型 training test val
    smilesList = dataset_smiles[smiles_name]# 每一行的smiles码

    # 遍历SMILES列表
    molecule_number = len(smilesList)  # 有多少分子
    for i, smiles in enumerate(smilesList):  # 枚举
        try:
            g= construct_RGCN_bigraph_from_smiles(smiles)  # 返回一个图
            mask = build_mask(labels.loc[i], mask_value=123456)  #
            molecule = [smiles, g,labels.loc[i], mask,
                        split_index.loc[i]]  # [simles码，图，标签值，是否是被填补的值，数据集类型]
            dataset_gnn.append(molecule)
            print('{}/{} molecule is transformed!'.format(i + 1, molecule_number))
        except:
            print('{} is transformed failed!'.format(smiles))
            molecule_number = molecule_number - 1
            failed_molecule.append(smiles)
    print('{}({}) is transformed failed!'.format(failed_molecule, len(failed_molecule)))
    return dataset_gnn



def load_graph_from_csv_bin_for_splited(
        bin_paths='example.bin',
        group_paths='example.npz',
        select_task_num=1,
        batch_size=1,
        category_list=None

):
    all_smiles,all_group,all_graphs,all_labels,all_masks,all_pos_g=[],[],[],[],[],[]
    labels_size = 0
    masks_size = 0
    for task_id, (group_path, bin_path,category) in enumerate(zip(group_paths, bin_paths,category_list)):
        print(group_path)
        data = np.load(group_path, allow_pickle=True)
        smiles = data['smiles']
        group = data['group']

        graphs, detailed_information = load_graphs(bin_path)  # 加载图以及标签信息
        labels = detailed_information['labels']
        mask = detailed_information['mask']
        valid_indices = np.where(mask)[0]  # 假设 mask 是一个布尔数组，True 表示有效样本
        valid_labels = labels[valid_indices]
        # 分层抽样划分数据集
        # 先划分训练集和临时数据集（测试集 + 验证集）
        if category=="classification":
            train_indices, temp_indices, _, _ = train_test_split(
                valid_indices, valid_labels, test_size=0.2, stratify=valid_labels, random_state=42
            )

            # 再从临时数据集中划分验证集和测试集
            val_indices, test_indices, _, _ = train_test_split(
                temp_indices, valid_labels[temp_indices - valid_indices[0]], test_size=0.5,
                stratify=valid_labels[temp_indices - valid_indices[0]], random_state=42
            )
            group[train_indices] = "training"

            group[val_indices] = "val"

            group[test_indices] = "test"
        # 计算每个图的节点数，并找出最大节点数
        max_node_count = max([g.num_nodes() for g in graphs])

        # calculate not_use index

        pos_g_list=[]
        for g in graphs:
            # 获取节点特征和坐标
            pos_g = DGLGraph()
            features = g.ndata['atom']  # 特征
            pos = g.ndata['pos']  # 坐标
            N = g.num_nodes()  # 原始节点数
            node_mask = torch.zeros(max_node_count)  # 初始化节点掩码

            # 填充掩码，表示实际的节点
            node_mask[:N] = 1

            # 如果原始矩阵小于目标大小，则填充0
            if N < max_node_count:
                # 计算需要填充的行数
                padding_size = max_node_count - features.shape[0]

                # 创建填充零的矩阵
                features_matrix = torch.cat((features, torch.zeros(padding_size, features.shape[1])), dim=0,)
                pos_matrix = torch.cat((pos, torch.zeros(padding_size, pos.shape[1])), dim=0)
            else:
                # 如果原始矩阵大于目标大小，则截断
                features_matrix = features[:max_node_count]
                pos_matrix = pos[:max_node_count]
            pos_g.add_nodes(max_node_count)  # 在图中生成与上述数量相同的节点
            # 更新节点特征和坐标
            pos_g.ndata['atom'] = features_matrix.float()
            pos_g.ndata['pos'] = pos_matrix.float()
            pos_g.add_edges(g.edges()[0], g.edges()[1])
            pos_g.edata["etype"]=g.edata["normal"].float()
            # 更新图的节点数和掩码
            pos_g.ndata['mask'] = node_mask.float()  # 掩码表示实际节点和填充节点
            pos_g_list.append(pos_g)
            # 更新图中的节点数目
            # g.num = torch.tensor([max_node_count])  # 确保节点数为 max_node_count
        graphs=np.array(graphs)
        pos_g=np.array(pos_g_list)
        all_smiles.extend(smiles)
        all_group.extend(group)
        all_graphs.extend(graphs)
        all_pos_g.extend(pos_g)
        all_labels.append(labels)
        all_masks.append(mask)
        labels_size += labels.size(0)
        masks_size += mask.size(0)
    all_smiles,all_group,all_graphs,all_pos_g=np.array(all_smiles),np.array(all_group),np.array(all_graphs),np.array(all_pos_g)
    labels = torch.full((labels_size, select_task_num), 123456.0, dtype=torch.float64)
    mask = torch.zeros((masks_size, select_task_num), dtype=torch.float64)
    len_labels = 0
    len_masks = 0
    for i in range(0, select_task_num):
        labels[len_labels:len_labels + all_labels[i].size(0), i] = all_labels[i].squeeze(1)
        mask[len_masks:len_masks + all_masks[i].size(0), i] = all_masks[i].squeeze(1)
        len_labels += all_labels[i].size(0)
        len_masks += all_masks[i].size(0)
    notuse_mask = torch.mean(mask.float(), 1).numpy().tolist()  # 计算每一行的平均值
    not_use_index = []
    for index, notuse in enumerate(notuse_mask):
        if notuse == 0:
            not_use_index.append(index)
    train_index = []
    val_index = []
    test_index = []
    for index, group_index in enumerate(all_group):  # index not in not_use_index去除没有数据的分子
        if group_index == 'training' and index not in not_use_index:
            train_index.append(index)
        if group_index == 'val' and index not in not_use_index:
            val_index.append(index)
        if group_index == 'test' and index not in not_use_index:
            test_index.append(index)
    target_index = val_index if len(val_index) > len(test_index) else test_index
    if target_index:
        train_index.append(target_index.pop())  # 从目标集合移动到训练集
    else:
        val_index.append(train_index.pop())  # 若无可用目标集合，从训练集中移出一项

    train_smiles, val_smiles, test_smiles = split_dataset_according_index(all_smiles, train_index, val_index, test_index)

    train_labels, val_labels, test_labels = split_dataset_according_index(labels.numpy(), train_index, val_index,
                                                                          test_index, data_type='pd')
    train_mask, val_mask, test_mask = split_dataset_according_index(mask.numpy(), train_index, val_index, test_index,
                                                                    data_type='pd')
    train_graph, val_graph, test_graph = split_dataset_according_index(all_graphs, train_index, val_index, test_index,)
    train_pos_g, val_pos_g, test_pos_g = split_dataset_according_index(all_pos_g, train_index, val_index, test_index, )
    # delete the 0_pos_label and 0_neg_label

    task_number = train_labels.values.shape[1]

    train_set = []
    val_set = []
    test_set = []

    for i in range(len(train_index)):
        # molecule = [train_smiles[i], train_graph[i], train_labels.values[i], train_mask.values[i],]
        molecule = [train_smiles[i], train_pos_g[i], train_graph[i], train_labels.values[i], train_mask.values[i]]
        train_set.append(molecule)

    for i in range(len(val_index)):
        # molecule = [val_smiles[i], val_graph[i], val_labels.values[i], val_mask.values[i], ]
        molecule = [val_smiles[i], val_pos_g[i], val_graph[i], val_labels.values[i], val_mask.values[i]]
        val_set.append(molecule)

    for i in range(len(test_index)):
        # molecule = [test_smiles[i], test_graph[i], test_labels.values[i], test_mask.values[i], ]
        molecule = [test_smiles[i], test_pos_g[i], test_graph[i], test_labels.values[i], test_mask.values[i]]
        test_set.append(molecule)
    print(len(train_set), len(val_set), len(test_set), task_number)
    return train_set, val_set, test_set, task_number


if __name__ == '__main__':
    path='../drug_prediction/'
    ls_ls=os.listdir(path)
    for i in ls_ls:
        if i.endswith('.csv'):
            i=i.split('.csv')[0]
            if i in ['drug_data']:
                data_path = path+ i + '.csv'
                save_path = path + i + '_tdc.bin'
                datanpz_path = path + i + '_group_tdc.npz'
                print(data_path)
                data_origin = pd.read_csv(data_path)
                smiles_name = 'SMILES'
                data_origin = data_origin.fillna(123456)  # 填充空值
                # labels_list = [x for x in data_origin.columns if x not in ['SMILES', 'group']]  # 读的是标签列名（‘Hepatotoxicity’）
                labels_list=['addictiveness']
                print(labels_list)
                data_set_gnn = multi_task_build_dataset(dataset_smiles=data_origin, labels_list=labels_list,
                                                        smiles_name=smiles_name)
                # 使用 map 和 zip 将 data_set_gnn 中的数据分别组合成独立的列表
                smiles, graphs,  labels, mask, split_index,  = map(list, zip(*data_set_gnn))
                graph_labels = {'labels': torch.tensor(labels),
                                'mask': torch.tensor(mask)
                                }  # labels是标签值，mask为0或1，表示是否是填补值
                np.savez(datanpz_path,  smiles=smiles, group=split_index, )
                save_graphs(save_path, graphs, graph_labels)  # 保存图
                print('Molecules graph is saved!')

    # train_set, val_set, test_set, task_number = load_graph_from_csv_bin_for_splited(
    #     bin_path=save_path,
    #     group_path=datanpz_path,
    #     select_task_index=None
    # )
