"""
BasinBreaker v3: Curvature Anomaly Detection + Directional Sharpening
=====================================================================
核心思想：持久性后门(SAM训练)的本质是后门参数处于异常平坦的basin中。
通过检测曲率异常(不需要知道trigger/target)，定向锐化，破坏平坦basin。

实验矩阵：
- Step 1 (曲率检测): A=逐参数 | B=逐层 | C=混合
- Step 2 (锐化策略): A=目标对齐 | B=相对提升 | C=FT逃逸验证
- Step 3 (防御微调): Anti-SAM fine-tuning (固定)
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
from datetime import datetime
from collections import OrderedDict

# ============================================================
# Part 1: Infrastructure (Model, Data, Evaluation)
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
                correct_bd += bd_predicted.eq(torch.full_like(labels[non_target], target_label)).sum().item()
                total_bd += non_target.sum().item()

    ca = 100.0 * correct_clean / total_clean
    asr = 100.0 * correct_bd / total_bd
    return ca, asr


def get_clean_loss(model, def_loader, device, n_batches=5):
    model.eval()
    total_loss = 0
    count = 0
    criterion = nn.CrossEntropyLoss()
    with torch.no_grad():
        for i, (images, labels) in enumerate(def_loader):
            if i >= n_batches:
                break
            images, labels = images.to(device), labels.to(device)
            outputs = model(images)
            total_loss += criterion(outputs, labels).item()
            count += 1
    return total_loss / max(count, 1)


# ============================================================
# Part 2: Step 1 — Curvature Estimation Methods
# ============================================================

def curvature_per_parameter(model, def_loader, device, eps=0.001, n_directions=2000):
    """
    方案A：逐参数曲率估计
    随机采样n_directions个方向，用有限差分估计每个参数的曲率
    κ(θ, d) ≈ [L(θ+εd) + L(θ-εd) - 2L(θ)] / ε²
    返回：每个参数的平均曲率值
    """
    print(f"  [Step1-A] Per-parameter curvature, eps={eps}, n_dirs={n_directions}")
    model.eval()
    criterion = nn.CrossEntropyLoss()

    params = []
    param_names = []
    for name, p in model.named_parameters():
        if p.requires_grad:
            params.append(p)
            param_names.append(name)

    total_params = sum(p.numel() for p in params)
    curvature_accum = [torch.zeros_like(p.data) for p in params]

    base_loss = get_clean_loss(model, def_loader, device, n_batches=3)

    for d_idx in range(n_directions):
        directions = [torch.randn_like(p.data) for p in params]
        dir_norm = torch.sqrt(sum((d**2).sum() for d in directions))
        directions = [d / dir_norm for d in directions]

        # L(θ + εd)
        for p, d in zip(params, directions):
            p.data.add_(d, alpha=eps)
        loss_plus = get_clean_loss(model, def_loader, device, n_batches=3)

        # L(θ - εd) (move -2ε from current)
        for p, d in zip(params, directions):
            p.data.add_(d, alpha=-2*eps)
        loss_minus = get_clean_loss(model, def_loader, device, n_batches=3)

        # Restore θ
        for p, d in zip(params, directions):
            p.data.add_(d, alpha=eps)

        curv = (loss_plus + loss_minus - 2 * base_loss) / (eps ** 2)

        for i, d in enumerate(directions):
            curvature_accum[i] += (d.abs() * curv)

        if (d_idx + 1) % 200 == 0:
            print(f"    Direction {d_idx+1}/{n_directions} done")

    curvature_map = {}
    for name, curv_acc in zip(param_names, curvature_accum):
        curvature_map[name] = (curv_acc / n_directions).abs()

    all_curvatures = torch.cat([c.flatten() for c in curvature_map.values()])
    mean_curv = all_curvatures.mean().item()
    std_curv = all_curvatures.std().item()
    threshold = mean_curv - 2 * std_curv

    anomaly_mask = {}
    n_anomaly = 0
    for name, curv in curvature_map.items():
        mask = curv < max(threshold, 0)
        anomaly_mask[name] = mask
        n_anomaly += mask.sum().item()

    print(f"    Mean curvature: {mean_curv:.6f}, Std: {std_curv:.6f}")
    print(f"    Threshold (μ-2σ): {threshold:.6f}")
    print(f"    Anomalous params: {n_anomaly}/{total_params} ({100*n_anomaly/total_params:.2f}%)")

    return anomaly_mask, curvature_map


def curvature_per_layer(model, def_loader, device, n_vectors=50):
    """
    方案B：逐层曲率估计 (Hutchinson trace estimator)
    Tr(H) ≈ (1/n) Σ vᵀHv，用随机向量v估计每层的Hessian trace
    返回：每层的曲率值 + 异常层mask
    """
    print(f"  [Step1-B] Per-layer curvature (Hutchinson), n_vectors={n_vectors}")
    model.eval()
    criterion = nn.CrossEntropyLoss()

    layer_curvatures = {}

    images_batch, labels_batch = None, None
    for images, labels in def_loader:
        images_batch, labels_batch = images.to(device), labels.to(device)
        break

    for name, param in model.named_parameters():
        if not param.requires_grad or param.numel() < 100:
            continue

        traces = []
        for _ in range(n_vectors):
            v = torch.randint(0, 2, param.shape, device=device).float() * 2 - 1

            model.zero_grad()
            outputs = model(images_batch)
            loss = criterion(outputs, labels_batch)
            grad = torch.autograd.grad(loss, param, create_graph=True)[0]

            gv = (grad * v).sum()
            hvp = torch.autograd.grad(gv, param, retain_graph=False)[0]
            trace_est = (v * hvp).sum().item()
            traces.append(trace_est)

        avg_trace = np.mean(traces) / param.numel()
        layer_curvatures[name] = avg_trace

    curv_values = np.array(list(layer_curvatures.values()))
    mean_curv = curv_values.mean()
    std_curv = curv_values.std()
    threshold = mean_curv - 2 * std_curv

    anomaly_layers = {}
    for name, curv in layer_curvatures.items():
        anomaly_layers[name] = curv < threshold

    n_anomaly = sum(1 for v in anomaly_layers.values() if v)
    print(f"    Layer curvatures: mean={mean_curv:.6f}, std={std_curv:.6f}")
    print(f"    Threshold: {threshold:.6f}")
    print(f"    Anomalous layers: {n_anomaly}/{len(anomaly_layers)}")

    anomaly_mask = {}
    for name, param in model.named_parameters():
        if name in anomaly_layers and anomaly_layers[name]:
            anomaly_mask[name] = torch.ones_like(param.data, dtype=torch.bool)
        else:
            anomaly_mask[name] = torch.zeros_like(param.data, dtype=torch.bool)

    return anomaly_mask, layer_curvatures


def curvature_hybrid(model, def_loader, device, n_vectors_coarse=30, n_dirs_fine=500, eps=0.001):
    """
    方案C：混合策略
    第一步：逐层粗筛（Hutchinson），找出可疑层
    第二步：在可疑层内做逐参数细筛（有限差分）
    """
    print(f"  [Step1-C] Hybrid: coarse layer screening + fine-grained param analysis")
    model.eval()
    criterion = nn.CrossEntropyLoss()

    # Phase 1: Coarse layer screening
    print("    Phase 1: Layer-level screening...")
    images_batch, labels_batch = None, None
    for images, labels in def_loader:
        images_batch, labels_batch = images.to(device), labels.to(device)
        break

    layer_curvatures = {}
    for name, param in model.named_parameters():
        if not param.requires_grad or param.numel() < 100:
            continue
        traces = []
        for _ in range(n_vectors_coarse):
            v = torch.randint(0, 2, param.shape, device=device).float() * 2 - 1
            model.zero_grad()
            outputs = model(images_batch)
            loss = criterion(outputs, labels_batch)
            grad = torch.autograd.grad(loss, param, create_graph=True)[0]
            gv = (grad * v).sum()
            hvp = torch.autograd.grad(gv, param, retain_graph=False)[0]
            traces.append((v * hvp).sum().item())
        layer_curvatures[name] = np.mean(traces) / param.numel()

    curv_values = np.array(list(layer_curvatures.values()))
    threshold_layer = curv_values.mean() - 1.5 * curv_values.std()
    suspect_layers = [n for n, c in layer_curvatures.items() if c < threshold_layer]
    print(f"    Suspect layers: {len(suspect_layers)}/{len(layer_curvatures)}")

    # Phase 2: Fine-grained analysis within suspect layers
    print("    Phase 2: Fine-grained param analysis in suspect layers...")
    anomaly_mask = {}
    base_loss = get_clean_loss(model, def_loader, device, n_batches=3)

    params_dict = dict(model.named_parameters())
    for name in suspect_layers:
        param = params_dict[name]
        curv_accum = torch.zeros_like(param.data)

        for _ in range(n_dirs_fine):
            d = torch.randn_like(param.data)
            d = d / d.norm()

            param.data.add_(d, alpha=eps)
            loss_plus = get_clean_loss(model, def_loader, device, n_batches=2)
            param.data.add_(d, alpha=-2*eps)
            loss_minus = get_clean_loss(model, def_loader, device, n_batches=2)
            param.data.add_(d, alpha=eps)

            curv = abs(loss_plus + loss_minus - 2 * base_loss) / (eps ** 2)
            curv_accum += d.abs() * curv

        curv_avg = curv_accum / n_dirs_fine
        layer_mean = curv_avg.mean()
        layer_std = curv_avg.std()
        mask = curv_avg < (layer_mean - 1.5 * layer_std)
        anomaly_mask[name] = mask

    for name, param in model.named_parameters():
        if name not in anomaly_mask:
            anomaly_mask[name] = torch.zeros_like(param.data, dtype=torch.bool)

    total_anomaly = sum(m.sum().item() for m in anomaly_mask.values())
    total_params = sum(p.numel() for p in model.parameters() if p.requires_grad)
    print(f"    Total anomalous params: {total_anomaly}/{total_params} ({100*total_anomaly/total_params:.2f}%)")

    return anomaly_mask, layer_curvatures


# ============================================================
# Part 3: Step 2 — Directional Sharpening Strategies
# ============================================================

def sharpen_target_alignment(model, anomaly_mask, def_loader, device,
                             lr=0.001, max_steps=30, target_multiplier=5.0):
    """
    策略A：目标曲率对齐
    将异常低曲率区域的曲率提升到正常均值水平
    通过在异常方向上做 sharpness ascent 实现
    """
    print(f"  [Step2-A] Target alignment sharpening, lr={lr}, steps={max_steps}")
    model.train()
    criterion = nn.CrossEntropyLoss()

    masked_params = []
    for name, param in model.named_parameters():
        if name in anomaly_mask and anomaly_mask[name].any():
            masked_params.append((name, param, anomaly_mask[name]))

    if not masked_params:
        print("    No anomalous params found, skipping sharpening")
        return model

    for step in range(max_steps):
        for images, labels in def_loader:
            images, labels = images.to(device), labels.to(device)
            break

        model.zero_grad()
        outputs = model(images)
        loss = criterion(outputs, labels)
        loss.backward()

        with torch.no_grad():
            for name, param, mask in masked_params:
                if param.grad is not None:
                    ascent_dir = param.grad * mask.float()
                    ascent_norm = ascent_dir.norm()
                    if ascent_norm > 0:
                        ascent_dir = ascent_dir / ascent_norm
                        param.data.add_(ascent_dir, alpha=lr)

        if (step + 1) % 10 == 0:
            cur_loss = get_clean_loss(model, def_loader, device, n_batches=3)
            print(f"    Step {step+1}/{max_steps}, loss={cur_loss:.4f}")

    return model


def sharpen_relative_amplification(model, anomaly_mask, def_loader, device,
                                   lr=0.002, max_steps=30, amplification=10.0):
    """
    策略B：相对曲率提升
    在异常方向上施加更强的扰动，使曲率相对提升5-10倍
    使用交替的 ascent/descent 步骤制造局部不稳定性
    """
    print(f"  [Step2-B] Relative amplification, lr={lr}, steps={max_steps}, amp={amplification}")
    model.train()
    criterion = nn.CrossEntropyLoss()

    masked_params = []
    for name, param in model.named_parameters():
        if name in anomaly_mask and anomaly_mask[name].any():
            masked_params.append((name, param, anomaly_mask[name]))

    if not masked_params:
        print("    No anomalous params found, skipping")
        return model

    for step in range(max_steps):
        for images, labels in def_loader:
            images, labels = images.to(device), labels.to(device)
            break

        # Ascent step: maximize loss in anomalous directions
        model.zero_grad()
        outputs = model(images)
        loss = criterion(outputs, labels)
        loss.backward()

        with torch.no_grad():
            for name, param, mask in masked_params:
                if param.grad is not None:
                    grad_masked = param.grad * mask.float()
                    grad_norm = grad_masked.norm()
                    if grad_norm > 0:
                        # Amplified ascent in anomalous directions
                        param.data.add_(grad_masked / grad_norm, alpha=lr * amplification)

        # Descent step: minimize loss in normal directions (preserve CA)
        model.zero_grad()
        outputs = model(images)
        loss = criterion(outputs, labels)
        loss.backward()

        with torch.no_grad():
            for name, param, mask in masked_params:
                if param.grad is not None:
                    grad_normal = param.grad * (~mask).float()
                    grad_norm = grad_normal.norm()
                    if grad_norm > 0:
                        param.data.add_(grad_normal / grad_norm, alpha=-lr)

        if (step + 1) % 10 == 0:
            cur_loss = get_clean_loss(model, def_loader, device, n_batches=3)
            print(f"    Step {step+1}/{max_steps}, loss={cur_loss:.4f}")

    return model


def sharpen_ft_escape(model, anomaly_mask, def_loader, device,
                      lr=0.001, max_steps=30, ft_lr=0.01, escape_threshold=0.1):
    """
    策略C：FT逃逸验证
    模拟一步FT，检查参数位移是否超过阈值
    如果位移不够（说明仍在平坦basin中），继续锐化
    目标：使模拟FT后的参数位移足够大（能逃出basin）
    """
    print(f"  [Step2-C] FT escape verification, lr={lr}, steps={max_steps}, threshold={escape_threshold}")
    model.train()
    criterion = nn.CrossEntropyLoss()

    masked_params = []
    for name, param in model.named_parameters():
        if name in anomaly_mask and anomaly_mask[name].any():
            masked_params.append((name, param, anomaly_mask[name]))

    if not masked_params:
        print("    No anomalous params found, skipping")
        return model

    for step in range(max_steps):
        # Save current params
        saved_params = {name: param.data.clone() for name, param, _ in masked_params}

        # Simulate one FT step
        for images, labels in def_loader:
            images, labels = images.to(device), labels.to(device)
            break

        model.zero_grad()
        outputs = model(images)
        loss = criterion(outputs, labels)
        loss.backward()

        with torch.no_grad():
            for name, param, mask in masked_params:
                if param.grad is not None:
                    param.data.add_(param.grad * mask.float(), alpha=-ft_lr)

        # Measure displacement
        displacement = 0
        for name, param, mask in masked_params:
            diff = (param.data - saved_params[name]) * mask.float()
            displacement += diff.norm().item()

        # Restore params
        for name, param, _ in masked_params:
            param.data.copy_(saved_params[name])

        if displacement > escape_threshold:
            print(f"    Step {step+1}: displacement={displacement:.4f} > threshold, basin broken!")
            break

        # If displacement too small, do sharpness ascent to break flatness
        model.zero_grad()
        outputs = model(images)
        loss = criterion(outputs, labels)
        loss.backward()

        with torch.no_grad():
            for name, param, mask in masked_params:
                if param.grad is not None:
                    ascent = param.grad * mask.float()
                    ascent_norm = ascent.norm()
                    if ascent_norm > 0:
                        param.data.add_(ascent / ascent_norm, alpha=lr)

        if (step + 1) % 10 == 0:
            print(f"    Step {step+1}/{max_steps}, displacement={displacement:.4f}")

    return model


# ============================================================
# Part 4: Step 3 — Anti-SAM Fine-Tuning
# ============================================================

def anti_sam_finetune(model, def_loader, device, epochs=30, lr=0.005, rho=0.05):
    """
    Anti-SAM微调：SAM的逆操作
    SAM: 先找到loss最大的方向(ascent)，再在该点做descent → 寻找平坦区域
    Anti-SAM: 先找到loss最小的方向(descent)，再在该点做ascent → 逃离平坦区域

    具体实现：
    1. 计算梯度 g
    2. 沿 -g 方向走一步（找到更平坦的点）
    3. 在该点计算新梯度，沿新梯度方向做正常descent
    效果：倾向于走向更尖锐的区域，破坏SAM创造的平坦basin
    """
    print(f"  [Step3] Anti-SAM fine-tuning, epochs={epochs}, lr={lr}, rho={rho}")
    model.train()
    criterion = nn.CrossEntropyLoss()
    optimizer = optim.SGD(model.parameters(), lr=lr, momentum=0.9, weight_decay=5e-4)

    for epoch in range(epochs):
        total_loss = 0
        n_batches = 0

        for images, labels in def_loader:
            images, labels = images.to(device), labels.to(device)

            # Step 1: Compute gradient at current point
            optimizer.zero_grad()
            outputs = model(images)
            loss = criterion(outputs, labels)
            loss.backward()

            # Step 2: Move to SHARPEST direction (opposite of SAM)
            # SAM moves to max-loss neighbor; Anti-SAM moves to min-loss neighbor
            with torch.no_grad():
                grad_norm = torch.sqrt(sum(
                    (p.grad ** 2).sum() for p in model.parameters() if p.grad is not None
                ))
                for p in model.parameters():
                    if p.grad is not None:
                        # Move AGAINST gradient (toward lower loss = flatter region)
                        # Then compute gradient there (which points away from flat region)
                        p.data.sub_(rho * p.grad / (grad_norm + 1e-12))

            # Step 3: Compute gradient at the perturbed point
            optimizer.zero_grad()
            outputs = model(images)
            loss2 = criterion(outputs, labels)
            loss2.backward()

            # Step 4: Restore parameters and apply the "escape" gradient
            with torch.no_grad():
                # First restore
                grad_norm2 = torch.sqrt(sum(
                    (p.grad ** 2).sum() for p in model.parameters() if p.grad is not None
                ))
                for p in model.parameters():
                    if p.grad is not None:
                        # Restore from perturbation
                        p.data.add_(rho * p.grad / (grad_norm2 + 1e-12))

            # Normal optimizer step with the gradient from perturbed point
            optimizer.step()

            total_loss += loss2.item()
            n_batches += 1

        avg_loss = total_loss / max(n_batches, 1)
        if (epoch + 1) % 5 == 0:
            print(f"    Epoch {epoch+1}/{epochs}, avg_loss={avg_loss:.4f}")

    return model


# ============================================================
# Part 5: Main Experiment Runner
# ============================================================

def run_single_config(config_name, step1_method, step2_method, model_path,
                      def_loader, test_loader, device, log_dir):
    """运行单个配置的完整实验流程"""
    print(f"\n{'='*60}")
    print(f"Config: {config_name}")
    print(f"  Step1: {step1_method}, Step2: {step2_method}")
    print(f"{'='*60}")

    # Load attack model
    model = ResNet18(num_classes=10).to(device)
    state_dict = torch.load(model_path, map_location=device)
    model.load_state_dict(state_dict)

    ca_init, asr_init = evaluate(model, test_loader, device)
    print(f"  Initial: CA={ca_init:.2f}%, ASR={asr_init:.2f}%")

    results = {
        'config': config_name,
        'step1': step1_method,
        'step2': step2_method,
        'initial_ca': ca_init,
        'initial_asr': asr_init,
    }

    # Step 1: Curvature anomaly detection
    print(f"\n  === Step 1: Curvature Analysis ({step1_method}) ===")
    t0 = time.time()

    if step1_method == 'per_parameter':
        anomaly_mask, curv_info = curvature_per_parameter(
            model, def_loader, device, eps=0.001, n_directions=500)
    elif step1_method == 'per_layer':
        anomaly_mask, curv_info = curvature_per_layer(
            model, def_loader, device, n_vectors=50)
    elif step1_method == 'hybrid':
        anomaly_mask, curv_info = curvature_hybrid(
            model, def_loader, device, n_vectors_coarse=30, n_dirs_fine=200)
    else:
        raise ValueError(f"Unknown step1 method: {step1_method}")

    step1_time = time.time() - t0
    results['step1_time'] = step1_time
    n_anomaly = sum(m.sum().item() for m in anomaly_mask.values())
    total_p = sum(p.numel() for p in model.parameters() if p.requires_grad)
    results['anomaly_ratio'] = n_anomaly / total_p
    print(f"  Step 1 done in {step1_time:.1f}s, anomaly ratio: {results['anomaly_ratio']:.4f}")

    # Evaluate after Step 1 (should be unchanged)
    ca_s1, asr_s1 = evaluate(model, test_loader, device)
    results['post_step1_ca'] = ca_s1
    results['post_step1_asr'] = asr_s1

    # Step 2: Directional sharpening
    print(f"\n  === Step 2: Directional Sharpening ({step2_method}) ===")
    t0 = time.time()

    if step2_method == 'target_alignment':
        model = sharpen_target_alignment(model, anomaly_mask, def_loader, device,
                                         lr=0.001, max_steps=30)
    elif step2_method == 'relative_amplification':
        model = sharpen_relative_amplification(model, anomaly_mask, def_loader, device,
                                               lr=0.002, max_steps=30, amplification=10.0)
    elif step2_method == 'ft_escape':
        model = sharpen_ft_escape(model, anomaly_mask, def_loader, device,
                                  lr=0.001, max_steps=30, escape_threshold=0.1)
    else:
        raise ValueError(f"Unknown step2 method: {step2_method}")

    step2_time = time.time() - t0
    results['step2_time'] = step2_time

    ca_s2, asr_s2 = evaluate(model, test_loader, device)
    results['post_step2_ca'] = ca_s2
    results['post_step2_asr'] = asr_s2
    print(f"  After Step 2: CA={ca_s2:.2f}%, ASR={asr_s2:.2f}% (time={step2_time:.1f}s)")

    # Step 3: Anti-SAM fine-tuning
    print(f"\n  === Step 3: Anti-SAM Fine-Tuning ===")
    t0 = time.time()
    model = anti_sam_finetune(model, def_loader, device, epochs=30, lr=0.005, rho=0.05)
    step3_time = time.time() - t0

    ca_s3, asr_s3 = evaluate(model, test_loader, device)
    results['post_step3_ca'] = ca_s3
    results['post_step3_asr'] = asr_s3
    results['step3_time'] = step3_time
    print(f"  After Step 3: CA={ca_s3:.2f}%, ASR={asr_s3:.2f}% (time={step3_time:.1f}s)")

    # Persistence test: continue clean FT for 20 epochs
    print(f"\n  === Persistence Test: 20 epochs clean FT ===")
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
    results['final_ca'] = ca_final
    results['final_asr'] = asr_final
    results['total_time'] = step1_time + step2_time + step3_time
    print(f"  Final (after 20ep FT): CA={ca_final:.2f}%, ASR={asr_final:.2f}%")

    # Save results
    result_path = os.path.join(log_dir, f"result_{config_name}.json")
    with open(result_path, 'w') as f:
        json.dump(results, f, indent=2)

    return results


def main():
    print("=" * 70)
    print("BasinBreaker v3: Curvature Anomaly Detection + Directional Sharpening")
    print("=" * 70)
    print(f"Start time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    print(f"Device: {device}")

    # Paths
    model_path = '/root/workspace/aaai-backdoor/baselines/badnet+sbl/logs/0511_BasinBreaker防御实验/sam_attack_model_20260511_150527.pt'
    log_dir = f'/root/workspace/aaai-backdoor/baselines/badnet+sbl/logs/0511_BasinBreaker防御实验/v3_{datetime.now().strftime("%Y%m%d_%H%M%S")}'
    os.makedirs(log_dir, exist_ok=True)

    # Data
    print("\nLoading data...")
    def_loader, test_loader = prepare_data('/root/workspace/aaai-backdoor/datasets', batch_size=128)

    # Experiment matrix - 3 representative configs first
    configs = [
        ('1A', 'per_parameter', 'target_alignment'),
        ('2C', 'per_layer', 'ft_escape'),
        ('3A', 'hybrid', 'target_alignment'),
    ]

    all_results = []
    for config_name, step1, step2 in configs:
        result = run_single_config(
            config_name, step1, step2, model_path,
            def_loader, test_loader, device, log_dir
        )
        all_results.append(result)

    # Also run Standard FT baseline for comparison
    print(f"\n{'='*60}")
    print("Baseline: Standard FT (50 epochs)")
    print(f"{'='*60}")

    model = ResNet18(num_classes=10).to(device)
    state_dict = torch.load(model_path, map_location=device)
    model.load_state_dict(state_dict)

    model.train()
    optimizer = optim.SGD(model.parameters(), lr=0.005, momentum=0.9, weight_decay=5e-4)
    criterion = nn.CrossEntropyLoss()
    for epoch in range(50):
        for images, labels in def_loader:
            images, labels = images.to(device), labels.to(device)
            optimizer.zero_grad()
            outputs = model(images)
            loss = criterion(outputs, labels)
            loss.backward()
            optimizer.step()

    ca_ft, asr_ft = evaluate(model, test_loader, device)
    ft_result = {'config': 'StandardFT', 'final_ca': ca_ft, 'final_asr': asr_ft}
    all_results.append(ft_result)
    print(f"  Standard FT: CA={ca_ft:.2f}%, ASR={asr_ft:.2f}%")

    # Summary
    print(f"\n{'='*70}")
    print("SUMMARY")
    print(f"{'='*70}")
    print(f"{'Config':<10} {'Post-S2 CA':>10} {'Post-S2 ASR':>11} {'Post-S3 CA':>10} {'Post-S3 ASR':>11} {'Final CA':>9} {'Final ASR':>10}")
    print("-" * 75)
    for r in all_results:
        if r['config'] == 'StandardFT':
            print(f"{'StdFT':<10} {'—':>10} {'—':>11} {'—':>10} {'—':>11} {r['final_ca']:>8.2f}% {r['final_asr']:>9.2f}%")
        else:
            print(f"{r['config']:<10} {r['post_step2_ca']:>9.2f}% {r['post_step2_asr']:>10.2f}% "
                  f"{r['post_step3_ca']:>9.2f}% {r['post_step3_asr']:>10.2f}% "
                  f"{r['final_ca']:>8.2f}% {r['final_asr']:>9.2f}%")

    # Save all results
    summary_path = os.path.join(log_dir, 'all_results.json')
    with open(summary_path, 'w') as f:
        json.dump(all_results, f, indent=2)
    print(f"\nResults saved to: {log_dir}")
    print(f"End time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")


if __name__ == '__main__':
    main()
