"""
BasinBreaker v3.2: LR Sweep + Hybrid Strategies
================================================
v3.1发现：大LR(0.05)是唯一能破坏SAM持久性的方法(ASR: 99.88→1.92%)
但CA损失较大(93→86%)。

本实验：
1. LR扫描：找到ASR/CA的最优平衡点
2. 渐进式LR：先大后小，先逃出basin再恢复CA
3. 层选择性大LR：只对部分层用大LR
4. 大LR + 知识蒸馏：用原模型的clean输出做soft label保护CA
"""

import torch
import torch.nn as nn
import torch.nn.functional as F
import torch.optim as optim
import torchvision
import torchvision.transforms as transforms
from torch.utils.data import DataLoader, Subset
import numpy as np
import os
import time
import json
import copy
from datetime import datetime


class BasicBlock(nn.Module):
    expansion = 1
    def __init__(self, in_planes, planes, stride=1):
        super().__init__()
        self.conv1 = nn.Conv2d(in_planes, planes, 3, stride=stride, padding=1, bias=False)
        self.bn1 = nn.BatchNorm2d(planes)
        self.conv2 = nn.Conv2d(planes, planes, 3, stride=1, padding=1, bias=False)
        self.bn2 = nn.BatchNorm2d(planes)
        self.shortcut = nn.Sequential()
        if stride != 1 or in_planes != self.expansion * planes:
            self.shortcut = nn.Sequential(
                nn.Conv2d(in_planes, self.expansion * planes, 1, stride=stride, bias=False),
                nn.BatchNorm2d(self.expansion * planes))
    def forward(self, x):
        out = F.relu(self.bn1(self.conv1(x)))
        out = self.bn2(self.conv2(out))
        out += self.shortcut(x)
        return F.relu(out)


class ResNet18(nn.Module):
    def __init__(self, num_classes=10):
        super().__init__()
        self.in_planes = 64
        self.conv1 = nn.Conv2d(3, 64, 3, stride=1, padding=1, bias=False)
        self.bn1 = nn.BatchNorm2d(64)
        self.layer1 = self._make_layer(64, 2, stride=1)
        self.layer2 = self._make_layer(128, 2, stride=2)
        self.layer3 = self._make_layer(256, 2, stride=2)
        self.layer4 = self._make_layer(512, 2, stride=2)
        self.linear = nn.Linear(512, num_classes)

    def _make_layer(self, planes, num_blocks, stride):
        strides = [stride] + [1] * (num_blocks - 1)
        layers = []
        for s in strides:
            layers.append(BasicBlock(self.in_planes, planes, s))
            self.in_planes = planes * BasicBlock.expansion
        return nn.Sequential(*layers)

    def forward(self, x):
        out = F.relu(self.bn1(self.conv1(x)))
        out = self.layer1(out)
        out = self.layer2(out)
        out = self.layer3(out)
        out = self.layer4(out)
        out = F.adaptive_avg_pool2d(out, (1, 1))
        out = out.view(out.size(0), -1)
        return self.linear(out)


def add_trigger(images, patch_size=3):
    triggered = images.clone()
    triggered[:, :, -patch_size:, -patch_size:] = 1.0
    return triggered


def prepare_data(data_root='./data', batch_size=128):
    transform_train = transforms.Compose([
        transforms.RandomCrop(32, padding=4),
        transforms.RandomHorizontalFlip(),
        transforms.ToTensor(),
        transforms.Normalize((0.4914, 0.4822, 0.4465), (0.2023, 0.1994, 0.2010)),
    ])
    transform_test = transforms.Compose([
        transforms.ToTensor(),
        transforms.Normalize((0.4914, 0.4822, 0.4465), (0.2023, 0.1994, 0.2010)),
    ])
    trainset = torchvision.datasets.CIFAR10(root=data_root, train=True, download=True, transform=transform_train)
    testset = torchvision.datasets.CIFAR10(root=data_root, train=False, download=True, transform=transform_test)
    n = len(trainset)
    indices = list(range(n))
    np.random.seed(42)
    np.random.shuffle(indices)
    n_attack = int(0.85 * n)
    n_clean = int(0.10 * n)
    def_indices = indices[n_attack + n_clean:]
    def_set = Subset(trainset, def_indices)
    def_loader = DataLoader(def_set, batch_size=batch_size, shuffle=True, num_workers=2)
    test_loader = DataLoader(testset, batch_size=batch_size, shuffle=False, num_workers=2)
    return def_loader, test_loader


def evaluate(model, test_loader, device, target_label=0):
    model.eval()
    correct_clean = 0
    correct_bd = 0
    total_clean = 0
    total_bd = 0
    with torch.no_grad():
        for images, labels in test_loader:
            images, labels = images.to(device), labels.to(device)
            outputs = model(images)
            _, predicted = outputs.max(1)
            correct_clean += predicted.eq(labels).sum().item()
            total_clean += labels.size(0)
            non_target = labels != target_label
            if non_target.sum() > 0:
                bd_images = add_trigger(images[non_target])
                bd_outputs = model(bd_images)
                _, bd_predicted = bd_outputs.max(1)
                correct_bd += bd_predicted.eq(
                    torch.full_like(labels[non_target], target_label)).sum().item()
                total_bd += non_target.sum().item()
    ca = 100.0 * correct_clean / total_clean
    asr = 100.0 * correct_bd / total_bd
    return ca, asr


# ============================================================
# Experiment 1: LR Sweep
# ============================================================

def ft_with_lr(model, def_loader, device, lr, epochs=50):
    """Standard FT with given LR + cosine schedule"""
    model.train()
    criterion = nn.CrossEntropyLoss()
    optimizer = optim.SGD(model.parameters(), lr=lr, momentum=0.9, weight_decay=5e-4)
    scheduler = optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=epochs)
    for epoch in range(epochs):
        for images, labels in def_loader:
            images, labels = images.to(device), labels.to(device)
            optimizer.zero_grad()
            outputs = model(images)
            loss = criterion(outputs, labels)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=5.0)
            optimizer.step()
        scheduler.step()
    return model


# ============================================================
# Experiment 2: Progressive LR (先大后小)
# ============================================================

def progressive_lr_ft(model, def_loader, device, high_lr=0.05, low_lr=0.005,
                      high_epochs=10, low_epochs=40):
    """先用大LR逃出basin，再用小LR恢复CA"""
    model.train()
    criterion = nn.CrossEntropyLoss()

    # Phase 1: Large LR escape
    optimizer = optim.SGD(model.parameters(), lr=high_lr, momentum=0.9, weight_decay=5e-4)
    for epoch in range(high_epochs):
        for images, labels in def_loader:
            images, labels = images.to(device), labels.to(device)
            optimizer.zero_grad()
            outputs = model(images)
            loss = criterion(outputs, labels)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=5.0)
            optimizer.step()

    # Phase 2: Small LR recovery
    optimizer = optim.SGD(model.parameters(), lr=low_lr, momentum=0.9, weight_decay=5e-4)
    scheduler = optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=low_epochs)
    for epoch in range(low_epochs):
        for images, labels in def_loader:
            images, labels = images.to(device), labels.to(device)
            optimizer.zero_grad()
            outputs = model(images)
            loss = criterion(outputs, labels)
            loss.backward()
            optimizer.step()
        scheduler.step()

    return model


# ============================================================
# Experiment 3: Layer-Selective Large LR
# ============================================================

def layer_selective_ft(model, def_loader, device, high_lr=0.05, low_lr=0.005,
                       epochs=50, high_layers='later'):
    """只对部分层用大LR，其他层用小LR"""
    model.train()
    criterion = nn.CrossEntropyLoss()

    # Split parameters into high-LR and low-LR groups
    high_params = []
    low_params = []
    for name, param in model.named_parameters():
        if high_layers == 'later':
            if 'layer3' in name or 'layer4' in name or 'linear' in name:
                high_params.append(param)
            else:
                low_params.append(param)
        elif high_layers == 'earlier':
            if 'conv1' in name or 'bn1' in name or 'layer1' in name or 'layer2' in name:
                high_params.append(param)
            else:
                low_params.append(param)

    optimizer = optim.SGD([
        {'params': high_params, 'lr': high_lr},
        {'params': low_params, 'lr': low_lr},
    ], momentum=0.9, weight_decay=5e-4)
    scheduler = optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=epochs)

    for epoch in range(epochs):
        for images, labels in def_loader:
            images, labels = images.to(device), labels.to(device)
            optimizer.zero_grad()
            outputs = model(images)
            loss = criterion(outputs, labels)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=5.0)
            optimizer.step()
        scheduler.step()

    return model


# ============================================================
# Experiment 4: Large LR + Knowledge Distillation
# ============================================================

def distill_ft(model, def_loader, device, lr=0.05, epochs=50, temperature=4.0, alpha=0.7):
    """大LR FT + 用原模型clean输出做soft label保护CA"""
    teacher = copy.deepcopy(model)
    teacher.eval()
    for p in teacher.parameters():
        p.requires_grad = False

    model.train()
    optimizer = optim.SGD(model.parameters(), lr=lr, momentum=0.9, weight_decay=5e-4)
    scheduler = optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=epochs)
    criterion_hard = nn.CrossEntropyLoss()

    for epoch in range(epochs):
        for images, labels in def_loader:
            images, labels = images.to(device), labels.to(device)
            optimizer.zero_grad()

            student_out = model(images)
            with torch.no_grad():
                teacher_out = teacher(images)

            # Hard loss (CE with true labels)
            loss_hard = criterion_hard(student_out, labels)

            # Soft loss (KD with teacher)
            loss_soft = F.kl_div(
                F.log_softmax(student_out / temperature, dim=1),
                F.softmax(teacher_out / temperature, dim=1),
                reduction='batchmean'
            ) * (temperature ** 2)

            loss = alpha * loss_soft + (1 - alpha) * loss_hard
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=5.0)
            optimizer.step()
        scheduler.step()

    return model


# ============================================================
# Main
# ============================================================

def run_single(name, defense_fn, model_path, def_loader, test_loader, device):
    model = ResNet18(num_classes=10).to(device)
    state_dict = torch.load(model_path, map_location=device)
    model.load_state_dict(state_dict)

    ca_init, asr_init = evaluate(model, test_loader, device)

    t0 = time.time()
    model = defense_fn(model, def_loader, device)
    t1 = time.time()

    ca_post, asr_post = evaluate(model, test_loader, device)

    # Persistence test
    model.train()
    optimizer = optim.SGD(model.parameters(), lr=0.005, momentum=0.9, weight_decay=5e-4)
    criterion = nn.CrossEntropyLoss()
    for epoch in range(20):
        for images, labels in def_loader:
            images, labels = images.to(device), labels.to(device)
            optimizer.zero_grad()
            outputs = model(images)
            loss = criterion(outputs, labels)
            loss.backward()
            optimizer.step()

    ca_final, asr_final = evaluate(model, test_loader, device)

    print(f"  {name:<30} Post: CA={ca_post:.2f}% ASR={asr_post:.2f}% | "
          f"Final: CA={ca_final:.2f}% ASR={asr_final:.2f}% | {t1-t0:.1f}s")

    return {
        'name': name, 'post_ca': ca_post, 'post_asr': asr_post,
        'final_ca': ca_final, 'final_asr': asr_final, 'time': t1-t0
    }


def main():
    print("=" * 70)
    print("BasinBreaker v3.2: LR Sweep + Hybrid Strategies")
    print("=" * 70)
    print(f"Start: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    model_path = '/root/workspace/aaai-backdoor/baselines/badnet+sbl/logs/0511_BasinBreaker防御实验/sam_attack_model_20260511_150527.pt'
    log_dir = f'/root/workspace/aaai-backdoor/baselines/badnet+sbl/logs/0511_BasinBreaker防御实验/v3.2_{datetime.now().strftime("%Y%m%d_%H%M%S")}'
    os.makedirs(log_dir, exist_ok=True)

    def_loader, test_loader = prepare_data('/root/workspace/aaai-backdoor/datasets', batch_size=128)

    # Verify initial model
    model = ResNet18(num_classes=10).to(device)
    model.load_state_dict(torch.load(model_path, map_location=device))
    ca, asr = evaluate(model, test_loader, device)
    print(f"\nAttack model: CA={ca:.2f}%, ASR={asr:.2f}%")
    del model

    print(f"\n{'='*70}")
    print("Experiment 1: LR Sweep")
    print(f"{'='*70}")

    all_results = []
    for lr in [0.005, 0.01, 0.02, 0.03, 0.05, 0.08, 0.1]:
        r = run_single(f'FT_lr{lr}',
                       lambda m, dl, dev, _lr=lr: ft_with_lr(m, dl, dev, _lr, epochs=50),
                       model_path, def_loader, test_loader, device)
        all_results.append(r)

    print(f"\n{'='*70}")
    print("Experiment 2: Progressive LR")
    print(f"{'='*70}")

    for high_ep in [5, 10, 15, 20]:
        r = run_single(f'Progressive_h{high_ep}ep',
                       lambda m, dl, dev, _he=high_ep: progressive_lr_ft(
                           m, dl, dev, high_lr=0.05, low_lr=0.005,
                           high_epochs=_he, low_epochs=50-_he),
                       model_path, def_loader, test_loader, device)
        all_results.append(r)

    print(f"\n{'='*70}")
    print("Experiment 3: Layer-Selective LR")
    print(f"{'='*70}")

    r = run_single('LayerSel_later_high',
                   lambda m, dl, dev: layer_selective_ft(m, dl, dev, high_lr=0.05,
                       low_lr=0.005, epochs=50, high_layers='later'),
                   model_path, def_loader, test_loader, device)
    all_results.append(r)

    r = run_single('LayerSel_earlier_high',
                   lambda m, dl, dev: layer_selective_ft(m, dl, dev, high_lr=0.05,
                       low_lr=0.005, epochs=50, high_layers='earlier'),
                   model_path, def_loader, test_loader, device)
    all_results.append(r)

    print(f"\n{'='*70}")
    print("Experiment 4: Distillation + Large LR")
    print(f"{'='*70}")

    for alpha in [0.3, 0.5, 0.7, 0.9]:
        r = run_single(f'Distill_lr0.05_a{alpha}',
                       lambda m, dl, dev, _a=alpha: distill_ft(m, dl, dev, lr=0.05,
                           epochs=50, temperature=4.0, alpha=_a),
                       model_path, def_loader, test_loader, device)
        all_results.append(r)

    # Summary
    print(f"\n{'='*70}")
    print("FULL SUMMARY")
    print(f"{'='*70}")
    print(f"{'Strategy':<30} {'Post CA':>8} {'Post ASR':>9} {'Final CA':>9} {'Final ASR':>10}")
    print("-" * 70)
    for r in all_results:
        print(f"{r['name']:<30} {r['post_ca']:>7.2f}% {r['post_asr']:>8.2f}% "
              f"{r['final_ca']:>8.2f}% {r['final_asr']:>9.2f}%")

    with open(os.path.join(log_dir, 'all_results.json'), 'w') as f:
        json.dump(all_results, f, indent=2)

    print(f"\nSaved to: {log_dir}")
    print(f"End: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")


if __name__ == '__main__':
    main()
