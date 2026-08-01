from collections import defaultdict
import random

import numpy as np
import sys

from dgl import load_graphs

sys.path.append("..")
import build_dataset
import torch
from torch.optim import Adam
from torch.utils.data import DataLoader
from model import collate_molgraphs,  run_a_train_epoch_heterogeneous, \
    run_an_eval_epoch_heterogeneous, set_random_seed, MGA, pos_weight,EarlyStopping
import os
import time
import pandas as pd
from process import process_smiles, standardize_mol, save_test_set, load_test_set
import torch.nn.functional as F
args = {}
args['device'] = os.environ.get(
    "MOLP_PC_DEVICE",
    "cuda:3" if torch.cuda.is_available() else "cpu",
)
args['atom_data_field'] = 'atom'
args['bond_data_field'] = 'etype'
args['classification_metric_name'] = 'roc_auc'
args['regression_metric_name'] = 'r2'
# model parameter
# model parameter

args['batch_size'] = 16
args['mode'] = 'higher'
args['in_feats'] = 40
args['hidden_feats'] = [128, 64, 32, 32]
args['classifier_hidden_feats'] = 128
args['drop_out'] = 0.2
args['loop'] = True
args['num_layers']=3
args['pooling']='sum'
model_list = ['Absorption', 'Distribution', 'Excretion', 'Metabolism',
              'Toxicology', 'Tox21', 'Ecotoxicity', 'LD50']
task_output_dims = {
    'Absorption': 1,
    'Distribution': 1,
    'Excretion': 1,
    'Metabolism': 1,
    'Toxicology': 1,
    'Tox21': 1,
    'Ecotoxicity': 1,
    'LD50': 1,
    'Predicted_Label': 3,
}
args['all_task_list'] = {
    'Absorption': ['F20', 'F30',  'HIA', 'PAMPA_NCATS', 'Pgp-inhibitor', 'Pgp-substrate','Caco2','MDCK Permeability', 'Lipophilicity_AstraZeneca' ,'Solubility_AqSolDB'],
                         'Distribution': ['BBB', 'Fu', 'PPB','VD'],
                         'Excretion': ["CL", 'T0.5'],
                         'Metabolism': ['CYP1A2 inhibitor', 'CYP1A2 substrate', 'CYP2C19 inhibitor', 'CYP2C19 substrate', 'CYP2C9 inhibitor', 'CYP2C9 substrate', 'CYP2D6 inhibitor', 'CYP2D6 substrate', 'CYP3A4 inhibitor', 'CYP3A4 substrate'],
                         'Toxicology': ['AMES', 'Carcinogenicity', 'ClinTox', 'DILI', 'Eye Corrosion', 'Eye Irritation', 'FDAMDD', 'H-HT-2', 'hERG',  'Respiratory', 'ROA', 'Skin Sensitization', ],
                         "Tox21":['NR-AhR', 'NR-AR-LBD', 'NR-AR', 'NR-Aromatase', 'NR-ER-LBD', 'NR-ER', 'NR-PPAR-gamma', 'SR-ARE', 'SR-ATAD5', 'SR-HSE', 'SR-MMP', 'SR-p53',],
                        "Ecotoxicity":['BCF', 'IGC50', 'LC50', 'LC50DM',],
                         "LD50":['LD50_zhu'],
                         "Predicted_Label":['Predicted_Label']
                         }
args['classification_tasks']=['Bioavailability_Ma', 'F20', 'F30', 'HIA', 'PAMPA_NCATS', 'Pgp-inhibitor', 'Pgp-substrate',
                              'BBB', 'Half_Life', 'T0.5', 'CYP1A2 inhibitor', 'CYP1A2 substrate', 'CYP2C19 inhibitor', 'CYP2C19 substrate',
                              'CYP2C9 inhibitor', 'CYP2C9 substrate', 'CYP2D6 inhibitor', 'CYP2D6 substrate', 'CYP3A4 inhibitor',
                              'CYP3A4 substrate', 'AMES', 'Carcinogenicity', 'ClinTox', 'DILI', 'Eye Corrosion', 'Eye Irritation',
                              'FDAMDD', 'H-HT-2', 'hERG',
                              'NR-AhR', 'NR-AR-LBD', 'NR-AR', 'NR-Aromatase', 'NR-ER-LBD', 'NR-ER', 'NR-PPAR-gamma', 'Respiratory', 'ROA',
                              'Skin Sensitization', 'SR-ARE', 'SR-ATAD5', 'SR-HSE', 'SR-MMP', 'SR-p53','PAMPA_NCATS','Pgp_Broccatelli','HIA_Hou','Bioavailability_Ma','Predicted_Label']

args['regression_tasks']=['Caco2', 'ESOL', 'Lipophilicity_AstraZeneca', 'MDCK Permeability',
                          'Solubility_AqSolDB', 'Fu', 'PPB', 'VD', 'Clearance_Hepatocyte_AZ','CL',
                          'Clearance_Microsome_AZ', 'BCF', 'IGC50', 'LC50', 'LC50DM','Caco2_Wang','HydrationFreeEnergy_FreeSolv','LD50_zhu']



def set_random_seed(seed=10):
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.backends.cudnn.benchmark = False
    torch.backends.cudnn.deterministic = True
    if torch.cuda.is_available():
        torch.cuda.manual_seed(seed)


def load_model_state(task_list, filename):
    if task_list in ['Absorption', "Distribution", "Toxicology", "Tox21", "LD50"]:
        return torch.load(filename, map_location=torch.device('cpu'))['model_state_dict']
    if task_list in ['Excretion', 'Ecotoxicity']:
        return torch.load(filename, map_location=torch.device('cpu')).state_dict()
    if task_list in ["Metabolism"]:
        return torch.load(filename, map_location=torch.device('cpu'))
    return torch.load("./model/drug_data_early_stop_atten_acc_weigth_seed8.pth",
                      map_location=torch.device('cpu')).state_dict()


def format_prediction(pred, index, task_idx, task_name, task_output_dim):
    start = task_idx * task_output_dim
    end = start + task_output_dim
    task_pred = pred[index, start:end]
    if task_name in args['classification_tasks']:
        if task_output_dim == 1:
            return float(torch.sigmoid(task_pred.squeeze()).item())
        probs = F.softmax(task_pred, dim=0)
        return int(torch.argmax(probs).item())
    return float(task_pred.squeeze().item())


def predict(path,name):
    df = pd.read_csv(path)
    df = standardize_mol(df)
    cache_path = f"{name}.pkl"
    if os.path.exists(cache_path):
        test_set = load_test_set(cache_path)
    else:
        test_set = process_smiles(df)
    test_loader = DataLoader(dataset=test_set,
                             batch_size=args['batch_size'],
                             collate_fn=collate_molgraphs)
    result_dict = defaultdict(dict)
    for task_list in model_list:
        args['select_task_list']=args['all_task_list'][task_list]
        args['select_task_list'] = sorted(
            args['select_task_list'],
            key=lambda task: (task not in args['classification_tasks'], task not in args['regression_tasks'])
        )
        model = MGA(in_feats=args['in_feats'], hidden_feats=args['hidden_feats'],
                    n_tasks=len(args['select_task_list']), classifier_hidden_feats=args['classifier_hidden_feats'],
                    dropout=args['drop_out'], loop=args['loop'], n_layers=args['num_layers'],
                    task_output_dim=task_output_dims.get(task_list, 1),
                    admet_backbone=task_list != 'Predicted_Label')

        filename=f'./model/{task_list}.pth'
        print(task_list)
        model.load_state_dict(load_model_state(task_list, filename))
        model.to(args['device'])
        model.eval()
        task_output_dim = task_output_dims.get(task_list, 1)
        set_random_seed(2025)
        with torch.no_grad():
            for batch_id, batch_data in enumerate(test_loader):
                # 解析批次数据（根据实际返回调整变量名）
                # 若batch_data包含labels/mask，可改为：smiles, pos_g, bg, labels, mask = batch_data
                smiles, pos_g, bg = batch_data

                # 移动数据到目标设备（含图结构及特征）
                pos_g = pos_g.to(args['device'])
                bg = bg.to(args['device'])
                # 确保图的边特征也移动到设备
                for key in pos_g.edata:
                    pos_g.edata[key] = pos_g.edata[key].to(args['device'])
                for key in bg.edata:
                    bg.edata[key] = bg.edata[key].to(args['device'])

                # 提取特征
                atom_feats = bg.ndata.pop(args['atom_data_field']).float().to(args['device'])
                bond_feats = bg.edata.pop(args['bond_data_field']).long().to(args['device'])

                # 模型预测
                pred= model(
                    smiles,
                    pos_g,
                    bg,
                    atom_feats,
                    bond_feats,
                    device=args['device'],
                    norm=None
                )
                for index, smile in enumerate(smiles):
                    # 为每个SMILES匹配对应的任务和预测值
                    for task_idx, task_name in enumerate(args['select_task_list']):
                        pred_value = format_prediction(
                            pred,
                            index,
                            task_idx,
                            task_name,
                            task_output_dim,
                        )
                        print(pred_value)
                        result_dict[smile][task_name] = pred_value
        # 导出为CSV
    df = pd.DataFrame(result_dict).T

    # 2. DataFrame转CSV（index=False 不保存行索引）
    df.to_csv("cb_data_result.csv", index=True, index_label="SMILES", encoding="utf-8")
if __name__ == '__main__':
    # print("www")
    # df=pd.read_csv("HQG_smiles_only.txt",sep="\t",header=None,names=['SMILES']  ) # 直接给唯一列命名为SMILES)
    # df.to_csv('test.csv',index=False,encoding="utf-8")
    predict('cb_data_fine.csv','cb1_data_fine')
