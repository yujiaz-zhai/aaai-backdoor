"""
BasinBreaker Defense Experiment on BadNet + SAM (CIFAR-10)
==========================================================
Part 1: Reproduce SAM-only attack + Standard FT defense (verify consistency with v2)
Part 2: BasinBreaker 4-step defense

Uses IDENTICAL settings to v2 experiment:
  - Data split: 85% attack (D0), 10% clean (D1), 5% defense
  - SAM training: 100 epochs, lr=0.01, rho=0.05
  - Standard FT defense: 50 epochs, lr=0.005
"""

import os, sys, json, time, copy, logging
from datetime import datetime

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
import torch.optim as optim
from torch.utils.data import DataLoader, Subset, Dataset
import torchvision
import torchvision.transforms as transforms

# ============================================================
# Logging
# ============================================================
LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs", "0511_BasinBreaker防御实验")
os.makedirs(LOG_DIR, exist_ok=True)
TIMESTAMP = datetime.now().strftime("%Y%m%d_%H%M%S")

def setup_logger(name):
    log_path = os.path.join(LOG_DIR, f"{name}_{TIMESTAMP}.log")
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    fh = logging.FileHandler(log_path)
    fh.setLevel(logging.INFO)
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    fh.setFormatter(fmt)
    ch.setFormatter(fmt)
    logger.addHandler(fh)
    logger.addHandler(ch)
    return logger

log = setup_logger("basin_breaker")

# ============================================================
# ResNet-18
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
# SAM Optimizer
# ============================================================
class SAM(torch.optim.Optimizer):
    def __init__(self, params, base_optimizer, rho=0.05, **kwargs):
        defaults = dict(rho=rho, **kwargs)
        super().__init__(params, defaults)
        self.base_optimizer = base_optimizer(self.param_groups, **kwargs)
        self.param_groups = self.base_optimizer.param_groups
        self.defaults.update(self.base_optimizer.defaults)
    @torch.no_grad()
    def first_step(self, zero_grad=False):
        grad_norm = self._grad_norm()
        for group in self.param_groups:
            scale = group["rho"] / (grad_norm + 1e-12)
            for p in group["params"]:
                if p.grad is None: continue
                self.state[p]["old_p"] = p.data.clone()
                p.add_(p.grad * scale.to(p))
        if zero_grad: self.zero_grad()
    @torch.no_grad()
    def second_step(self, zero_grad=False):
        for group in self.param_groups:
            for p in group["params"]:
                if p.grad is None: continue
                p.data = self.state[p]["old_p"]
        self.base_optimizer.step()
        if zero_grad: self.zero_grad()
    def _grad_norm(self):
        device = self.param_groups[0]["params"][0].device
        return torch.norm(torch.stack([
            p.grad.norm(p=2).to(device)
            for group in self.param_groups for p in group["params"]
            if p.grad is not None
        ]), p=2)

def disable_running_stats(model):
    for m in model.modules():
        if isinstance(m, nn.BatchNorm2d):
            m.backup_momentum = m.momentum
            m.momentum = 0

def enable_running_stats(model):
    for m in model.modules():
        if isinstance(m, nn.BatchNorm2d) and hasattr(m, "backup_momentum"):
            m.momentum = m.backup_momentum

# ============================================================
# Dataset
# ============================================================
class PoisonedCIFAR10(Dataset):
    def __init__(self, base_dataset, poison_indices, target_label=0):
        self.base = base_dataset
        self.poison_indices = set(poison_indices)
        self.target_label = target_label
    def __len__(self):
        return len(self.base)
    def __getitem__(self, idx):
        img, label = self.base[idx]
        is_poison = 1 if idx in self.poison_indices else 0
        if is_poison:
            img = self.apply_trigger(img.clone())
            label = self.target_label
        return img, label, is_poison
    @staticmethod
    def apply_trigger(img):
        img[:, -3:, -3:] = 1.0
        return img

def add_trigger_to_images(images):
    images = images.clone()
    images[:, :, -3:, -3:] = 1.0
    return images

# ============================================================
# Data Preparation (IDENTICAL to v2)
# ============================================================
def prepare_data(data_root, poison_rate=0.1, target_label=0, batch_size=128):
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
    train_set = torchvision.datasets.CIFAR10(root=data_root, train=True, download=False, transform=transform_train)
    test_set = torchvision.datasets.CIFAR10(root=data_root, train=False, download=False, transform=transform_test)

    n_train = len(train_set)
    indices = list(range(n_train))
    np.random.seed(42)
    np.random.shuffle(indices)

    n_d0 = int(0.85 * n_train)
    n_d1 = int(0.10 * n_train)
    idx_d0 = indices[:n_d0]
    idx_d1 = indices[n_d0:n_d0 + n_d1]
    idx_def = indices[n_d0 + n_d1:]  # 5% = 2500 samples

    poison_candidates = [i for i in idx_d0 if train_set.targets[i] != target_label]
    n_poison = int(poison_rate * n_d0)
    poison_indices = set(poison_candidates[:n_poison])

    log.info(f"Data split: D0={len(idx_d0)}, D1={len(idx_d1)}, Defense={len(idx_def)}")
    log.info(f"Poison samples: {len(poison_indices)} ({len(poison_indices)/len(idx_d0)*100:.1f}% of D0)")

    local_poison = set()
    for local_idx, global_idx in enumerate(idx_d0):
        if global_idx in poison_indices:
            local_poison.add(local_idx)
    d0_dataset = PoisonedCIFAR10(Subset(train_set, idx_d0), local_poison, target_label)

    def_base = Subset(train_set, idx_def)

    d0_loader = DataLoader(d0_dataset, batch_size=batch_size, shuffle=True, num_workers=4, pin_memory=True)
    def_loader = DataLoader(def_base, batch_size=batch_size, shuffle=True, num_workers=4, pin_memory=True)
    test_loader = DataLoader(test_set, batch_size=256, shuffle=False, num_workers=4, pin_memory=True)
    return d0_loader, def_loader, test_loader

# ============================================================
# Evaluation
# ============================================================
@torch.no_grad()
def evaluate(model, test_loader, device, target_label=0):
    model.eval()
    correct = total = asr_correct = asr_total = 0
    for images, labels in test_loader:
        images, labels = images.to(device), labels.to(device)
        outputs = model(images)
        _, predicted = outputs.max(1)
        total += labels.size(0)
        correct += predicted.eq(labels).sum().item()
        mask = labels != target_label
        if mask.sum() > 0:
            triggered = add_trigger_to_images(images[mask])
            _, pred_t = model(triggered).max(1)
            asr_total += mask.sum().item()
            asr_correct += (pred_t == target_label).sum().item()
    ca = 100.0 * correct / total
    asr = 100.0 * asr_correct / asr_total if asr_total > 0 else 0.0
    model.train()
    return ca, asr

# ============================================================
# SAM Attack Training (IDENTICAL to v2 train_sbl_step0)
# ============================================================
def train_sam_attack(model, d0_loader, epochs, lr, rho, device, test_loader):
    optimizer = SAM(model.parameters(), base_optimizer=optim.SGD, rho=rho,
                    lr=lr, momentum=0.9, weight_decay=5e-4)
    scheduler = optim.lr_scheduler.CosineAnnealingLR(optimizer.base_optimizer, T_max=epochs)
    criterion = nn.CrossEntropyLoss()
    log.info(f"=== SAM Attack Training: {epochs} epochs, lr={lr}, rho={rho} ===")
    for epoch in range(epochs):
        model.train()
        total_loss = 0
        for images, labels, _ in d0_loader:
            images, labels = images.to(device), labels.to(device)
            enable_running_stats(model)
            loss = criterion(model(images), labels)
            loss.backward()
            optimizer.first_step(zero_grad=True)
            disable_running_stats(model)
            loss2 = criterion(model(images), labels)
            loss2.backward()
            optimizer.second_step(zero_grad=True)
            total_loss += loss.item()
        scheduler.step()
        if (epoch + 1) % 10 == 0 or epoch == 0:
            ca, asr = evaluate(model, test_loader, device)
            log.info(f"  [SAM-Attack] Epoch {epoch+1}/{epochs}: loss={total_loss/len(d0_loader):.4f}, CA={ca:.2f}%, ASR={asr:.2f}%")
    ca, asr = evaluate(model, test_loader, device)
    log.info(f"  [SAM-Attack] Final: CA={ca:.2f}%, ASR={asr:.2f}%")
    return ca, asr

# ============================================================
# Standard FT Defense (IDENTICAL to v2)
# ============================================================
def standard_ft_defense(model, def_loader, epochs, lr, device, test_loader, label="FT-Defense"):
    optimizer = optim.SGD(model.parameters(), lr=lr, momentum=0.9, weight_decay=5e-4)
    criterion = nn.CrossEntropyLoss()
    results = []
    log.info(f"=== {label}: {epochs} epochs, lr={lr} ===")
    for epoch in range(epochs):
        model.train()
        for images, labels in def_loader:
            images, labels = images.to(device), labels.to(device)
            optimizer.zero_grad()
            loss = criterion(model(images), labels)
            loss.backward()
            optimizer.step()
        ca, asr = evaluate(model, test_loader, device)
        results.append((ca, asr))
        if (epoch + 1) % 5 == 0 or epoch == 0:
            log.info(f"  [{label}] Epoch {epoch+1}/{epochs}: CA={ca:.2f}%, ASR={asr:.2f}%")
    log.info(f"  [{label}] Final: CA={results[-1][0]:.2f}%, ASR={results[-1][1]:.2f}%")
    return results

# ============================================================
# BasinBreaker Defense (4 Steps) - FIXED VERSION
# ============================================================

def identify_backdoor_subspace(model, def_loader, device, target_label=0, top_ratio=0.1):
    """Step 1: Identify backdoor-related parameter subspace.
    
    Method: Compare gradient on clean data vs gradient on triggered data.
    Parameters where triggered gradient >> clean gradient are suspicious.
    """
    log.info("=== Step 1: Backdoor Subspace Identification ===")
    model.eval()
    criterion = nn.CrossEntropyLoss()
    
    # Accumulate clean gradients
    model.zero_grad()
    clean_grad_accum = None
    n_batches = 0
    for images, labels in def_loader:
        images, labels = images.to(device), labels.to(device)
        loss = criterion(model(images), labels)
        loss.backward()
        n_batches += 1
        if n_batches >= 5:
            break
    clean_grads = {}
    for name, p in model.named_parameters():
        if p.grad is not None:
            clean_grads[name] = p.grad.clone() / n_batches
    
    # Accumulate triggered gradients (toward target label)
    model.zero_grad()
    n_batches = 0
    for images, labels in def_loader:
        images, labels = images.to(device), labels.to(device)
        triggered = add_trigger_to_images(images)
        target_labels = torch.full_like(labels, target_label)
        loss = criterion(model(triggered), target_labels)
        loss.backward()
        n_batches += 1
        if n_batches >= 5:
            break
    triggered_grads = {}
    for name, p in model.named_parameters():
        if p.grad is not None:
            triggered_grads[name] = p.grad.clone() / n_batches
    
    # Score: |triggered_grad| / (|clean_grad| + eps)
    scores = {}
    all_scores = []
    for name in clean_grads:
        score = triggered_grads[name].abs() / (clean_grads[name].abs() + 1e-6)
        scores[name] = score
        all_scores.append(score.flatten())
    
    all_scores_cat = torch.cat(all_scores)
    threshold = torch.quantile(all_scores_cat, 1.0 - top_ratio)
    
    # Create binary mask
    masks = {}
    total_params = 0
    masked_params = 0
    for name in scores:
        mask = (scores[name] >= threshold).float()
        masks[name] = mask
        total_params += mask.numel()
        masked_params += mask.sum().item()
    
    log.info(f"  Subspace identified: {masked_params:.0f}/{total_params} params ({100*masked_params/total_params:.1f}%)")
    log.info(f"  Score threshold: {threshold:.4f}")
    model.train()
    return masks


def sharpness_ascent(model, def_loader, masks, device, target_label=0,
                     n_steps=20, ascent_eps=0.001, ascent_lr=0.0005, max_grad_norm=0.5):
    """Step 2: Orthogonal Sharpness Ascent (CONSERVATIVE version).
    
    Goal: Increase curvature (sharpness) in the backdoor subspace direction,
    making the backdoor basin sharper and thus easier to escape via fine-tuning.
    
    Key fixes from v1:
    - eps reduced 50x (0.05 -> 0.001)
    - lr reduced 20x (0.01 -> 0.0005)
    - Gradient clipping added (max_norm=0.5)
    - Loss monitored with early stopping if it diverges
    """
    log.info(f"=== Step 2: Sharpness Ascent (eps={ascent_eps}, lr={ascent_lr}, steps={n_steps}) ===")
    model.train()
    criterion = nn.CrossEntropyLoss()
    
    initial_sd = copy.deepcopy(model.state_dict())
    initial_ca, initial_asr = evaluate(model, iter([next(iter(def_loader))]), device)
    
    # Get a fixed batch for consistent evaluation
    eval_images, eval_labels = next(iter(def_loader))
    eval_images, eval_labels = eval_images.to(device), eval_labels.to(device)
    
    base_loss = criterion(model(eval_images), eval_labels).item()
    log.info(f"  Initial loss on eval batch: {base_loss:.4f}")
    
    for step in range(n_steps):
        # Get a training batch
        for images, labels in def_loader:
            images, labels = images.to(device), labels.to(device)
            break
        
        # 1. Perturb parameters in masked directions
        perturbation = {}
        model.zero_grad()
        loss_before = criterion(model(images), labels)
        loss_before.backward()
        
        for name, p in model.named_parameters():
            if name in masks and p.grad is not None:
                # Perturb in gradient direction, masked to backdoor subspace
                grad_masked = p.grad * masks[name]
                grad_norm = grad_masked.norm()
                if grad_norm > 1e-8:
                    perturbation[name] = ascent_eps * grad_masked / grad_norm
                else:
                    perturbation[name] = torch.zeros_like(p)
        
        # 2. Apply perturbation
        with torch.no_grad():
            for name, p in model.named_parameters():
                if name in perturbation:
                    p.add_(perturbation[name])
        
        # 3. Compute loss at perturbed point
        model.zero_grad()
        loss_perturbed = criterion(model(images), labels)
        loss_perturbed.backward()
        
        # 4. Restore original parameters
        with torch.no_grad():
            for name, p in model.named_parameters():
                if name in perturbation:
                    p.sub_(perturbation[name])
        
        # 5. Update: MAXIMIZE sharpness = move params so that the perturbed loss increases
        # This means we want the landscape to be SHARPER around current point
        # We do gradient ASCENT on the perturbed loss, masked to backdoor subspace
        with torch.no_grad():
            for name, p in model.named_parameters():
                if name in masks and p.grad is not None:
                    grad_masked = p.grad * masks[name]
                    # Clip gradient
                    grad_norm = grad_masked.norm()
                    if grad_norm > max_grad_norm:
                        grad_masked = grad_masked * (max_grad_norm / grad_norm)
                    # Gradient ASCENT (maximize sharpness)
                    p.add_(ascent_lr * grad_masked)
        
        # Monitor
        if (step + 1) % 5 == 0 or step == 0:
            with torch.no_grad():
                current_loss = criterion(model(eval_images), eval_labels).item()
            log.info(f"  Step {step+1}/{n_steps}: loss={current_loss:.4f} (base={base_loss:.4f})")
            
            # Early stopping: if loss explodes (>10x base), abort
            if current_loss > base_loss * 10:
                log.info(f"  WARNING: Loss diverging ({current_loss:.4f} > 10x base). Stopping early.")
                model.load_state_dict(initial_sd)
                log.info(f"  Restored to initial state.")
                return False
    
    ca_after, asr_after = evaluate(model, [next(iter(def_loader))], device)
    log.info(f"  After sharpness ascent: loss changed {base_loss:.4f} -> {current_loss:.4f}")
    return True


def subspace_reset(model, masks, device, noise_scale=0.001, reset_ratio=0.3):
    """Step 3: Subspace Reset - add noise to most suspicious parameters."""
    log.info(f"=== Step 3: Subspace Reset (noise={noise_scale}, ratio={reset_ratio}) ===")
    
    with torch.no_grad():
        total_reset = 0
        for name, p in model.named_parameters():
            if name in masks:
                mask = masks[name]
                # Only reset top reset_ratio of masked params (by mask value)
                n_masked = mask.sum().item()
                if n_masked > 0:
                    noise = torch.randn_like(p) * noise_scale * p.abs().mean()
                    p.add_(noise * mask)
                    total_reset += n_masked
    
    log.info(f"  Reset {total_reset:.0f} parameters with noise scale {noise_scale}")


def anti_rebound_training(model, def_loader, masks, device, target_label=0,
                          epochs=10, lr=0.001, alpha=1.0, beta=0.5):
    """Step 4: Anti-Rebound Training.
    
    Objective: min L_clean + alpha * L_away + beta * L_sharpness
    - L_clean: standard CE on clean data (maintain accuracy)
    - L_away: push triggered predictions AWAY from target (reduce ASR)
    - L_sharpness: penalize flat directions in backdoor subspace
    
    Fixed from v1: removed detach() so gradients flow properly.
    """
    log.info(f"=== Step 4: Anti-Rebound Training ({epochs} epochs, lr={lr}) ===")
    model.train()
    criterion = nn.CrossEntropyLoss()
    optimizer = optim.SGD(model.parameters(), lr=lr, momentum=0.9, weight_decay=5e-4)
    
    for epoch in range(epochs):
        total_loss = 0
        for images, labels in def_loader:
            images, labels = images.to(device), labels.to(device)
            optimizer.zero_grad()
            
            # L_clean: standard classification loss
            outputs = model(images)
            loss_clean = criterion(outputs, labels)
            
            # L_away: push triggered samples away from target
            triggered = add_trigger_to_images(images)
            outputs_triggered = model(triggered)
            # Maximize entropy on triggered outputs (make model uncertain about triggered)
            probs_triggered = F.softmax(outputs_triggered, dim=1)
            loss_away = -torch.mean(torch.sum(probs_triggered * torch.log(probs_triggered + 1e-8), dim=1))
            # Also directly penalize confidence on target class
            loss_target_conf = torch.mean(probs_triggered[:, target_label])
            
            # Combined loss
            loss = loss_clean + alpha * (-loss_away) + beta * loss_target_conf
            
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
            optimizer.step()
            total_loss += loss.item()
        
        if (epoch + 1) % 2 == 0 or epoch == 0:
            log.info(f"  [Anti-Rebound] Epoch {epoch+1}/{epochs}: loss={total_loss/len(def_loader):.4f}")
    
    log.info(f"  Anti-rebound training complete.")

# ============================================================
# Main
# ============================================================
def main():
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    log.info(f"Device: {device}")
    log.info(f"Experiment: BasinBreaker Defense on BadNet+SAM (CIFAR-10)")
    log.info(f"Log dir: {LOG_DIR}")
    
    DATA_ROOT = "/root/workspace/aaai-backdoor/datasets/"
    POISON_RATE = 0.1
    TARGET_LABEL = 0
    BATCH_SIZE = 128
    SAM_EPOCHS = 100
    SAM_LR = 0.01
    SAM_RHO = 0.05
    DEF_EPOCHS = 50
    DEF_LR = 0.005  # Same as v2
    
    log.info(f"Settings: poison_rate={POISON_RATE}, target={TARGET_LABEL}, ")
    log.info(f"  SAM: epochs={SAM_EPOCHS}, lr={SAM_LR}, rho={SAM_RHO}")
    log.info(f"  FT Defense: epochs={DEF_EPOCHS}, lr={DEF_LR}")
    
    # Prepare data
    d0_loader, def_loader, test_loader = prepare_data(
        DATA_ROOT, POISON_RATE, TARGET_LABEL, BATCH_SIZE)
    
    # =============================================
    # PART 1: SAM Attack + Standard FT (reproduce v2)
    # =============================================
    log.info("\n" + "="*60)
    log.info("PART 1: Reproduce SAM Attack + Standard FT Defense")
    log.info("="*60)
    
    model = ResNet18(num_classes=10).to(device)
    torch.manual_seed(42)
    model.apply(lambda m: m.reset_parameters() if hasattr(m, "reset_parameters") else None)
    
    # Train with SAM
    ca_attack, asr_attack = train_sam_attack(
        model, d0_loader, SAM_EPOCHS, SAM_LR, SAM_RHO, device, test_loader)
    
    # Save attack model
    attack_sd = copy.deepcopy(model.state_dict())
    torch.save(attack_sd, os.path.join(LOG_DIR, f"sam_attack_model_{TIMESTAMP}.pt"))
    log.info(f"Attack model saved. CA={ca_attack:.2f}%, ASR={asr_attack:.2f}%")
    
    # Standard FT defense (for comparison)
    model_ft = ResNet18(num_classes=10).to(device)
    model_ft.load_state_dict(attack_sd)
    ft_results = standard_ft_defense(
        model_ft, def_loader, DEF_EPOCHS, DEF_LR, device, test_loader, label="Standard-FT")
    
    log.info(f"\n--- Standard FT Results ---")
    log.info(f"  Before defense: CA={ca_attack:.2f}%, ASR={asr_attack:.2f}%")
    log.info(f"  After defense:  CA={ft_results[-1][0]:.2f}%, ASR={ft_results[-1][1]:.2f}%")
    log.info(f"  v2 reference:   CA=91.26%, ASR=91.37%")
    
    # =============================================
    # PART 2: BasinBreaker Defense
    # =============================================
    log.info("\n" + "="*60)
    log.info("PART 2: BasinBreaker Defense")
    log.info("="*60)
    
    # Start from fresh copy of attack model
    model_bb = ResNet18(num_classes=10).to(device)
    model_bb.load_state_dict(attack_sd)
    
    ca_before, asr_before = evaluate(model_bb, test_loader, device)
    log.info(f"Before BasinBreaker: CA={ca_before:.2f}%, ASR={asr_before:.2f}%")
    
    # Step 1: Identify backdoor subspace
    masks = identify_backdoor_subspace(model_bb, def_loader, device, TARGET_LABEL, top_ratio=0.1)
    
    ca_s1, asr_s1 = evaluate(model_bb, test_loader, device)
    log.info(f"After Step 1 (identification only): CA={ca_s1:.2f}%, ASR={asr_s1:.2f}%")
    
    # Step 2: Sharpness Ascent (conservative)
    success = sharpness_ascent(model_bb, def_loader, masks, device, TARGET_LABEL,
                               n_steps=20, ascent_eps=0.001, ascent_lr=0.0005, max_grad_norm=0.5)
    
    ca_s2, asr_s2 = evaluate(model_bb, test_loader, device)
    log.info(f"After Step 2 (sharpness ascent): CA={ca_s2:.2f}%, ASR={asr_s2:.2f}% (success={success})")
    
    # Step 3: Subspace Reset
    subspace_reset(model_bb, masks, device, noise_scale=0.001, reset_ratio=0.3)
    
    ca_s3, asr_s3 = evaluate(model_bb, test_loader, device)
    log.info(f"After Step 3 (subspace reset): CA={ca_s3:.2f}%, ASR={asr_s3:.2f}%")
    
    # Step 4: Anti-Rebound Training
    anti_rebound_training(model_bb, def_loader, masks, device, TARGET_LABEL,
                          epochs=10, lr=0.001, alpha=1.0, beta=0.5)
    
    ca_s4, asr_s4 = evaluate(model_bb, test_loader, device)
    log.info(f"After Step 4 (anti-rebound): CA={ca_s4:.2f}%, ASR={asr_s4:.2f}%")
    
    # =============================================
    # PART 3: Additional FT after BasinBreaker
    # =============================================
    log.info("\n" + "="*60)
    log.info("PART 3: Standard FT after BasinBreaker (test if sharpening helps)")
    log.info("="*60)
    
    bb_ft_results = standard_ft_defense(
        model_bb, def_loader, DEF_EPOCHS, DEF_LR, device, test_loader, label="BB+FT")
    
    # =============================================
    # Summary
    # =============================================
    log.info("\n" + "="*60)
    log.info("FINAL RESULTS SUMMARY")
    log.info("="*60)
    log.info(f"{'Stage':<35} {'CA (%)':<10} {'ASR (%)':<10}")
    log.info("-" * 55)
    log.info(f"{'Attack (BadNet+SAM)':<35} {ca_attack:<10.2f} {asr_attack:<10.2f}")
    log.info(f"{'Standard FT (50ep, lr=0.005)':<35} {ft_results[-1][0]:<10.2f} {ft_results[-1][1]:<10.2f}")
    log.info(f"{'BB Step1 (subspace ID)':<35} {ca_s1:<10.2f} {asr_s1:<10.2f}")
    log.info(f"{'BB Step2 (sharpness ascent)':<35} {ca_s2:<10.2f} {asr_s2:<10.2f}")
    log.info(f"{'BB Step3 (subspace reset)':<35} {ca_s3:<10.2f} {asr_s3:<10.2f}")
    log.info(f"{'BB Step4 (anti-rebound)':<35} {ca_s4:<10.2f} {asr_s4:<10.2f}")
    log.info(f"{'BB + FT (50ep)':<35} {bb_ft_results[-1][0]:<10.2f} {bb_ft_results[-1][1]:<10.2f}")
    
    # Save results
    results = {
        "attack": {"CA": ca_attack, "ASR": asr_attack},
        "standard_ft": {"CA": ft_results[-1][0], "ASR": ft_results[-1][1]},
        "bb_step1": {"CA": ca_s1, "ASR": asr_s1},
        "bb_step2": {"CA": ca_s2, "ASR": asr_s2},
        "bb_step3": {"CA": ca_s3, "ASR": asr_s3},
        "bb_step4": {"CA": ca_s4, "ASR": asr_s4},
        "bb_plus_ft": {"CA": bb_ft_results[-1][0], "ASR": bb_ft_results[-1][1]},
        "ft_trajectory": ft_results,
        "bb_ft_trajectory": bb_ft_results,
        "v2_reference": {"SAM_only_after_defense": {"CA": 91.26, "ASR": 91.37}},
    }
    
    results_path = os.path.join(LOG_DIR, f"results_{TIMESTAMP}.json")
    with open(results_path, "w") as f:
        json.dump(results, f, indent=2)
    log.info(f"\nResults saved to: {results_path}")
    log.info("EXPERIMENT COMPLETE")


if __name__ == "__main__":
    main()
