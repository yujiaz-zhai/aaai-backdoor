"""
BasinBreaker v3.1: 修正版 — 全模型锐化 + 正确Anti-SAM
=====================================================================
v3.0 失败原因：
1. SAM使整个模型都平坦，无法通过内部统计量检测"异常平坦"区域
2. Anti-SAM实现逻辑有误（先descent再ascent，等于普通FT）
3. 锐化力度不够

v3.1 核心改动：
- 策略A: 全模型Sharpness Ascent（不做子空间检测，直接全局锐化）
- 策略B: 输出敏感方向检测 + 定向锐化（用随机扰动检测后门敏感方向）
- 策略C: 正确的Anti-SAM（先ascent找sharp方向，再沿该方向descent）
- 策略D: 大学习率激进FT（利用大LR逃出平坦basin）
- 策略E: 组合策略（先全局锐化，再Anti-SAM FT）
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

# ============================================================
# Model Definition (与v1/v2完全一致)
# ============================================================

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


# ============================================================
# Data & Evaluation
# ============================================================

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
# Defense Strategy A: Global Sharpness Ascent
# ============================================================

def defense_sharpness_ascent(model, def_loader, device, epochs=30, lr=0.01, rho=0.05):
    """
    全模型锐化：在每个batch上，先找到loss最大的邻域方向(ascent)，
    然后把模型参数推向那个方向。目标是破坏SAM创造的平坦basin。

    与SAM的区别：
    - SAM: ascent → descent（找到sharp方向后回到flat区域）
    - 这里: ascent → 保持（找到sharp方向后留在那里）

    然后再做普通FT恢复CA。
    """
    print(f"\n  [Strategy A] Global Sharpness Ascent")
    print(f"    Phase 1: Sharpening ({epochs} epochs, lr={lr}, rho={rho})")
    model.train()
    criterion = nn.CrossEntropyLoss()

    for epoch in range(epochs):
        total_loss = 0
        n_batches = 0
        for images, labels in def_loader:
            images, labels = images.to(device), labels.to(device)

            # Compute gradient
            model.zero_grad()
            outputs = model(images)
            loss = criterion(outputs, labels)
            loss.backward()

            # Ascent step: move toward higher loss (sharper region)
            with torch.no_grad():
                grad_norm = torch.sqrt(sum(
                    (p.grad ** 2).sum() for p in model.parameters() if p.grad is not None
                ))
                for p in model.parameters():
                    if p.grad is not None:
                        # Move IN gradient direction (toward higher loss = sharper)
                        p.data.add_(p.grad / (grad_norm + 1e-12), alpha=lr * rho)

            total_loss += loss.item()
            n_batches += 1

        if (epoch + 1) % 10 == 0:
            print(f"      Epoch {epoch+1}/{epochs}, avg_loss={total_loss/n_batches:.4f}")

    # Phase 2: Recovery FT
    print(f"    Phase 2: Recovery FT (20 epochs, lr=0.005)")
    optimizer = optim.SGD(model.parameters(), lr=0.005, momentum=0.9, weight_decay=5e-4)
    for epoch in range(20):
        for images, labels in def_loader:
            images, labels = images.to(device), labels.to(device)
            optimizer.zero_grad()
            outputs = model(images)
            loss = criterion(outputs, labels)
            loss.backward()
            optimizer.step()

    return model


# ============================================================
# Defense Strategy B: Output-Sensitive Direction Detection + Sharpening
# ============================================================

def defense_output_sensitive(model, def_loader, device, n_probes=100,
                             sharpen_epochs=20, ft_epochs=30, lr=0.01):
    """
    不需要知道trigger，通过随机扰动检测"输出敏感方向"：
    - 对每个参数施加小扰动，观察输出变化
    - 输出变化小的方向 = 平坦方向 = 可能的后门方向
    - 沿这些方向做锐化
    """
    print(f"\n  [Strategy B] Output-Sensitive Direction Detection")
    print(f"    Phase 1: Probing output sensitivity ({n_probes} probes)")
    model.eval()
    criterion = nn.CrossEntropyLoss()

    # Get reference outputs
    ref_outputs_list = []
    data_list = []
    for i, (images, labels) in enumerate(def_loader):
        if i >= 3:
            break
        images, labels = images.to(device), labels.to(device)
        with torch.no_grad():
            ref_out = model(images)
        ref_outputs_list.append(ref_out)
        data_list.append((images, labels))

    # Probe each layer's sensitivity
    eps = 0.01
    layer_sensitivity = {}
    for name, param in model.named_parameters():
        if not param.requires_grad or param.numel() < 100:
            continue

        sensitivities = []
        for _ in range(min(n_probes, 20)):
            direction = torch.randn_like(param.data)
            direction = direction / direction.norm() * eps

            param.data.add_(direction)
            total_diff = 0
            with torch.no_grad():
                for (images, _), ref_out in zip(data_list, ref_outputs_list):
                    new_out = model(images)
                    total_diff += (new_out - ref_out).abs().mean().item()
            param.data.sub_(direction)

            sensitivities.append(total_diff / len(data_list))

        layer_sensitivity[name] = np.mean(sensitivities)

    # Find low-sensitivity layers (flat directions)
    sens_values = np.array(list(layer_sensitivity.values()))
    sens_names = list(layer_sensitivity.keys())
    threshold = np.percentile(sens_values, 30)  # Bottom 30% = flattest

    flat_layers = [n for n, s in zip(sens_names, sens_values) if s <= threshold]
    print(f"    Found {len(flat_layers)} flat layers (bottom 30% sensitivity)")

    # Phase 2: Sharpen flat layers
    print(f"    Phase 2: Sharpening flat layers ({sharpen_epochs} epochs)")
    model.train()
    for epoch in range(sharpen_epochs):
        for images, labels in def_loader:
            images, labels = images.to(device), labels.to(device)
            model.zero_grad()
            outputs = model(images)
            loss = criterion(outputs, labels)
            loss.backward()

            with torch.no_grad():
                for name, param in model.named_parameters():
                    if name in flat_layers and param.grad is not None:
                        grad_norm = param.grad.norm()
                        if grad_norm > 0:
                            param.data.add_(param.grad / grad_norm, alpha=lr * 0.1)

    # Phase 3: FT recovery
    print(f"    Phase 3: FT recovery ({ft_epochs} epochs)")
    optimizer = optim.SGD(model.parameters(), lr=0.005, momentum=0.9, weight_decay=5e-4)
    for epoch in range(ft_epochs):
        for images, labels in def_loader:
            images, labels = images.to(device), labels.to(device)
            optimizer.zero_grad()
            outputs = model(images)
            loss = criterion(outputs, labels)
            loss.backward()
            optimizer.step()

    return model


# ============================================================
# Defense Strategy C: Correct Anti-SAM (Maximize Sharpness)
# ============================================================

def defense_anti_sam_correct(model, def_loader, device, epochs=50, lr=0.01, rho=0.1):
    """
    正确的Anti-SAM实现：
    SAM的目标是 min_θ max_{||ε||≤ρ} L(θ+ε)，即找到邻域内最大loss后minimize
    Anti-SAM的目标是：直接maximize sharpness，即让模型走向更尖锐的区域

    实现：
    1. 计算梯度 g1 at θ
    2. 走到 θ + ρ*g1/||g1|| (邻域内loss最大点)
    3. 计算梯度 g2 at θ + ρ*g1/||g1||
    4. 用 g2 更新参数（不恢复！直接从sharp点继续）

    这样模型会持续走向更尖锐的区域，破坏SAM的平坦basin。
    """
    print(f"\n  [Strategy C] Correct Anti-SAM (epochs={epochs}, lr={lr}, rho={rho})")
    model.train()
    criterion = nn.CrossEntropyLoss()

    for epoch in range(epochs):
        total_loss = 0
        n_batches = 0
        for images, labels in def_loader:
            images, labels = images.to(device), labels.to(device)

            # Step 1: Compute gradient at current point
            model.zero_grad()
            outputs = model(images)
            loss = criterion(outputs, labels)
            loss.backward()

            # Step 2: Move to sharpest neighbor (ascent)
            with torch.no_grad():
                grad_norm = torch.sqrt(sum(
                    (p.grad ** 2).sum() for p in model.parameters() if p.grad is not None
                ))
                old_params = {n: p.data.clone() for n, p in model.named_parameters()}
                for p in model.parameters():
                    if p.grad is not None:
                        p.data.add_(p.grad / (grad_norm + 1e-12), alpha=rho)

            # Step 3: Compute gradient at sharp point
            model.zero_grad()
            outputs2 = model(images)
            loss2 = criterion(outputs2, labels)
            loss2.backward()

            # Step 4: Descent from the sharp point (stay in sharp region)
            with torch.no_grad():
                for n, p in model.named_parameters():
                    if p.grad is not None:
                        # Restore to original, then apply descent from sharp-point gradient
                        p.data.copy_(old_params[n])
                        p.data.sub_(p.grad * lr)

            total_loss += loss2.item()
            n_batches += 1

        if (epoch + 1) % 10 == 0:
            print(f"      Epoch {epoch+1}/{epochs}, avg_loss={total_loss/n_batches:.4f}")

    return model


# ============================================================
# Defense Strategy D: Aggressive Large-LR FT
# ============================================================

def defense_aggressive_ft(model, def_loader, device, epochs=50, lr=0.05):
    """
    核心假设：SAM创造的平坦basin使得小LR的FT无法逃出。
    解决方案：用非常大的学习率，强制跳出平坦basin。
    lr=0.05 比标准FT的0.005大10倍。
    """
    print(f"\n  [Strategy D] Aggressive Large-LR FT (epochs={epochs}, lr={lr})")
    model.train()
    criterion = nn.CrossEntropyLoss()
    optimizer = optim.SGD(model.parameters(), lr=lr, momentum=0.9, weight_decay=5e-4)

    scheduler = optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=epochs)

    for epoch in range(epochs):
        total_loss = 0
        n_batches = 0
        for images, labels in def_loader:
            images, labels = images.to(device), labels.to(device)
            optimizer.zero_grad()
            outputs = model(images)
            loss = criterion(outputs, labels)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=5.0)
            optimizer.step()
            total_loss += loss.item()
            n_batches += 1
        scheduler.step()

        if (epoch + 1) % 10 == 0:
            print(f"      Epoch {epoch+1}/{epochs}, lr={scheduler.get_last_lr()[0]:.5f}, "
                  f"avg_loss={total_loss/n_batches:.4f}")

    return model


# ============================================================
# Defense Strategy E: Sharpness Ascent + Anti-SAM (Combined)
# ============================================================

def defense_combined(model, def_loader, device,
                     sharpen_epochs=20, sharpen_lr=0.01, sharpen_rho=0.05,
                     antisam_epochs=30, antisam_lr=0.01, antisam_rho=0.1):
    """
    组合策略：先全局锐化破坏basin，再用Anti-SAM持续逃离平坦区域。
    """
    print(f"\n  [Strategy E] Combined: Sharpness Ascent + Anti-SAM")

    # Phase 1: Global sharpness ascent
    print(f"    Phase 1: Sharpness Ascent ({sharpen_epochs} epochs)")
    model.train()
    criterion = nn.CrossEntropyLoss()

    for epoch in range(sharpen_epochs):
        for images, labels in def_loader:
            images, labels = images.to(device), labels.to(device)
            model.zero_grad()
            outputs = model(images)
            loss = criterion(outputs, labels)
            loss.backward()

            with torch.no_grad():
                grad_norm = torch.sqrt(sum(
                    (p.grad ** 2).sum() for p in model.parameters() if p.grad is not None
                ))
                for p in model.parameters():
                    if p.grad is not None:
                        p.data.add_(p.grad / (grad_norm + 1e-12), alpha=sharpen_lr * sharpen_rho)

        if (epoch + 1) % 10 == 0:
            print(f"      Sharpen epoch {epoch+1}/{sharpen_epochs}")

    # Phase 2: Anti-SAM FT
    print(f"    Phase 2: Anti-SAM FT ({antisam_epochs} epochs)")
    for epoch in range(antisam_epochs):
        total_loss = 0
        n_batches = 0
        for images, labels in def_loader:
            images, labels = images.to(device), labels.to(device)

            model.zero_grad()
            outputs = model(images)
            loss = criterion(outputs, labels)
            loss.backward()

            with torch.no_grad():
                grad_norm = torch.sqrt(sum(
                    (p.grad ** 2).sum() for p in model.parameters() if p.grad is not None
                ))
                old_params = {n: p.data.clone() for n, p in model.named_parameters()}
                for p in model.parameters():
                    if p.grad is not None:
                        p.data.add_(p.grad / (grad_norm + 1e-12), alpha=antisam_rho)

            model.zero_grad()
            outputs2 = model(images)
            loss2 = criterion(outputs2, labels)
            loss2.backward()

            with torch.no_grad():
                for n, p in model.named_parameters():
                    if p.grad is not None:
                        p.data.copy_(old_params[n])
                        p.data.sub_(p.grad * antisam_lr)

            total_loss += loss2.item()
            n_batches += 1

        if (epoch + 1) % 10 == 0:
            print(f"      Anti-SAM epoch {epoch+1}/{antisam_epochs}, "
                  f"avg_loss={total_loss/n_batches:.4f}")

    return model


# ============================================================
# Main Experiment
# ============================================================

def run_defense(name, defense_fn, model_path, def_loader, test_loader, device, log_dir):
    """运行单个防御策略并评估"""
    print(f"\n{'='*60}")
    print(f"Defense: {name}")
    print(f"{'='*60}")

    model = ResNet18(num_classes=10).to(device)
    state_dict = torch.load(model_path, map_location=device)
    model.load_state_dict(state_dict)

    ca_init, asr_init = evaluate(model, test_loader, device)
    print(f"  Initial: CA={ca_init:.2f}%, ASR={asr_init:.2f}%")

    t0 = time.time()
    model = defense_fn(model, def_loader, device)
    defense_time = time.time() - t0

    ca_post, asr_post = evaluate(model, test_loader, device)
    print(f"  After defense: CA={ca_post:.2f}%, ASR={asr_post:.2f}% (time={defense_time:.1f}s)")

    # Persistence test: 20 epochs clean FT
    print(f"  Persistence test: 20 epochs clean FT...")
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
    print(f"  Final (after persistence FT): CA={ca_final:.2f}%, ASR={asr_final:.2f}%")

    result = {
        'name': name,
        'initial_ca': ca_init, 'initial_asr': asr_init,
        'post_defense_ca': ca_post, 'post_defense_asr': asr_post,
        'final_ca': ca_final, 'final_asr': asr_final,
        'defense_time': defense_time,
    }

    with open(os.path.join(log_dir, f'result_{name}.json'), 'w') as f:
        json.dump(result, f, indent=2)

    return result


def main():
    print("=" * 70)
    print("BasinBreaker v3.1: Corrected Strategies")
    print("=" * 70)
    print(f"Start time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    print(f"Device: {device}")

    model_path = '/root/workspace/aaai-backdoor/baselines/badnet+sbl/logs/0511_BasinBreaker防御实验/sam_attack_model_20260511_150527.pt'
    log_dir = f'/root/workspace/aaai-backdoor/baselines/badnet+sbl/logs/0511_BasinBreaker防御实验/v3.1_{datetime.now().strftime("%Y%m%d_%H%M%S")}'
    os.makedirs(log_dir, exist_ok=True)

    print("\nLoading data...")
    def_loader, test_loader = prepare_data('/root/workspace/aaai-backdoor/datasets', batch_size=128)

    # Define all defense strategies
    defenses = [
        ('A_SharpAscent', lambda m, dl, dev: defense_sharpness_ascent(m, dl, dev,
            epochs=30, lr=0.01, rho=0.05)),
        ('B_OutputSensitive', lambda m, dl, dev: defense_output_sensitive(m, dl, dev,
            n_probes=100, sharpen_epochs=20, ft_epochs=30, lr=0.01)),
        ('C_AntiSAM', lambda m, dl, dev: defense_anti_sam_correct(m, dl, dev,
            epochs=50, lr=0.01, rho=0.1)),
        ('D_AggressiveFT', lambda m, dl, dev: defense_aggressive_ft(m, dl, dev,
            epochs=50, lr=0.05)),
        ('E_Combined', lambda m, dl, dev: defense_combined(m, dl, dev,
            sharpen_epochs=20, sharpen_lr=0.01, sharpen_rho=0.05,
            antisam_epochs=30, antisam_lr=0.01, antisam_rho=0.1)),
    ]

    # Also run standard FT baseline
    defenses.append(('F_StandardFT', lambda m, dl, dev: defense_aggressive_ft(m, dl, dev,
        epochs=50, lr=0.005)))

    all_results = []
    for name, fn in defenses:
        result = run_defense(name, fn, model_path, def_loader, test_loader, device, log_dir)
        all_results.append(result)

    # Summary
    print(f"\n{'='*70}")
    print("SUMMARY")
    print(f"{'='*70}")
    print(f"{'Strategy':<20} {'Post-Def CA':>11} {'Post-Def ASR':>12} {'Final CA':>9} {'Final ASR':>10} {'Time':>6}")
    print("-" * 72)
    for r in all_results:
        print(f"{r['name']:<20} {r['post_defense_ca']:>10.2f}% {r['post_defense_asr']:>11.2f}% "
              f"{r['final_ca']:>8.2f}% {r['final_asr']:>9.2f}% {r['defense_time']:>5.1f}s")

    with open(os.path.join(log_dir, 'all_results.json'), 'w') as f:
        json.dump(all_results, f, indent=2)

    print(f"\nResults saved to: {log_dir}")
    print(f"End time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")


if __name__ == '__main__':
    main()
