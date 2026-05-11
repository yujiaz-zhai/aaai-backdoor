"""
BasinBreaker Defense v2 - Aggressive but Controlled
====================================================
Key changes from v1:
  - Step 2: eps=0.01, lr=0.003 (middle ground between 0.001 and 0.05)
  - Step 3: Much more aggressive reset (noise_scale=0.1, or zero-out top params)
  - Step 4: Redesigned loss - direct backdoor unlearning (maximize loss on triggered->target)
  - Added: Multiple hyperparameter configs to sweep
  
Reuses the attack model from v1 run to save time.
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
    for h in logger.handlers[:]:
        logger.removeHandler(h)
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

log = setup_logger("basin_breaker_v2")

# ============================================================
# Model
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
    idx_def = indices[n_d0 + n_d1:]

    poison_candidates = [i for i in idx_d0 if train_set.targets[i] != target_label]
    n_poison = int(poison_rate * n_d0)
    poison_indices = set(poison_candidates[:n_poison])

    log.info(f"Data split: D0={len(idx_d0)}, Defense={len(idx_def)}")
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
# SAM Attack Training
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
        if (epoch + 1) % 20 == 0 or epoch == 0:
            ca, asr = evaluate(model, test_loader, device)
            log.info(f"  [SAM-Attack] Epoch {epoch+1}/{epochs}: loss={total_loss/len(d0_loader):.4f}, CA={ca:.2f}%, ASR={asr:.2f}%")
    ca, asr = evaluate(model, test_loader, device)
    log.info(f"  [SAM-Attack] Final: CA={ca:.2f}%, ASR={asr:.2f}%")
    return ca, asr

# ============================================================
# Standard FT Defense
# ============================================================
def standard_ft_defense(model, def_loader, epochs, lr, device, test_loader, label="FT"):
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
        if (epoch + 1) % 10 == 0 or epoch == 0:
            log.info(f"  [{label}] Epoch {epoch+1}/{epochs}: CA={ca:.2f}%, ASR={asr:.2f}%")
    return results

# ============================================================
# BasinBreaker v2 - Core Defense Steps
# ============================================================

def identify_backdoor_subspace(model, def_loader, device, target_label=0, top_ratio=0.1):
    """Step 1: Identify backdoor subspace via gradient difference."""
    log.info("=== Step 1: Backdoor Subspace Identification ===")
    model.eval()
    criterion = nn.CrossEntropyLoss()
    
    # Clean gradient
    model.zero_grad()
    n_batches = 0
    for images, labels in def_loader:
        images, labels = images.to(device), labels.to(device)
        loss = criterion(model(images), labels)
        loss.backward()
        n_batches += 1
        if n_batches >= 10:
            break
    clean_grads = {}
    for name, p in model.named_parameters():
        if p.grad is not None:
            clean_grads[name] = p.grad.clone() / n_batches
    
    # Triggered gradient (toward target)
    model.zero_grad()
    n_batches = 0
    for images, labels in def_loader:
        images, labels = images.to(device), labels.to(device)
        triggered = add_trigger_to_images(images)
        target_labels = torch.full_like(labels, target_label)
        loss = criterion(model(triggered), target_labels)
        loss.backward()
        n_batches += 1
        if n_batches >= 10:
            break
    triggered_grads = {}
    for name, p in model.named_parameters():
        if p.grad is not None:
            triggered_grads[name] = p.grad.clone() / n_batches
    
    # Score: gradient difference magnitude
    scores = {}
    all_scores = []
    for name in clean_grads:
        diff = (triggered_grads[name] - clean_grads[name]).abs()
        scores[name] = diff
        all_scores.append(diff.flatten())
    
    all_scores_cat = torch.cat(all_scores)
    threshold = torch.quantile(all_scores_cat, 1.0 - top_ratio)
    
    masks = {}
    total_params = 0
    masked_params = 0
    for name in scores:
        mask = (scores[name] >= threshold).float()
        masks[name] = mask
        total_params += mask.numel()
        masked_params += mask.sum().item()
    
    log.info(f"  Subspace: {masked_params:.0f}/{total_params} params ({100*masked_params/total_params:.1f}%)")
    model.train()
    return masks


def sharpness_ascent_v2(model, def_loader, masks, device, target_label=0,
                        n_steps=30, ascent_eps=0.01, ascent_lr=0.003, max_grad_norm=1.0):
    """Step 2: Sharpness Ascent v2 - stronger but with adaptive control.
    
    Strategy: Use SAM-like perturbation but in REVERSE direction in backdoor subspace.
    Instead of finding flat minima, we find sharp directions and push toward them.
    """
    log.info(f"=== Step 2: Sharpness Ascent v2 (eps={ascent_eps}, lr={ascent_lr}, steps={n_steps}) ===")
    model.train()
    criterion = nn.CrossEntropyLoss()
    
    initial_sd = copy.deepcopy(model.state_dict())
    
    for step in range(n_steps):
        # Get batch
        for images, labels in def_loader:
            images, labels = images.to(device), labels.to(device)
            break
        
        # Forward pass to get gradient direction
        model.zero_grad()
        loss = criterion(model(images), labels)
        loss.backward()
        
        # Compute masked perturbation (normalized per-parameter)
        perturbation = {}
        for name, p in model.named_parameters():
            if name in masks and p.grad is not None:
                grad_masked = p.grad * masks[name]
                param_norm = p.data.norm()
                if param_norm > 1e-8:
                    # Scale perturbation relative to parameter magnitude
                    perturbation[name] = ascent_eps * (grad_masked / (grad_masked.norm() + 1e-8)) * param_norm
                else:
                    perturbation[name] = torch.zeros_like(p)
        
        # Apply perturbation temporarily
        with torch.no_grad():
            for name, p in model.named_parameters():
                if name in perturbation:
                    p.add_(perturbation[name])
        
        # Compute loss at perturbed point
        model.zero_grad()
        loss_perturbed = criterion(model(images), labels)
        loss_perturbed.backward()
        
        # Restore
        with torch.no_grad():
            for name, p in model.named_parameters():
                if name in perturbation:
                    p.sub_(perturbation[name])
        
        # Gradient ascent on perturbed loss (maximize sharpness)
        with torch.no_grad():
            for name, p in model.named_parameters():
                if name in masks and p.grad is not None:
                    grad_masked = p.grad * masks[name]
                    grad_norm = grad_masked.norm()
                    if grad_norm > max_grad_norm:
                        grad_masked = grad_masked * (max_grad_norm / grad_norm)
                    p.add_(ascent_lr * grad_masked)
        
        if (step + 1) % 10 == 0 or step == 0:
            with torch.no_grad():
                check_loss = criterion(model(images), labels).item()
            ca_check, asr_check = evaluate(model, [next(iter(def_loader))], device)
            log.info(f"  Step {step+1}/{n_steps}: loss={check_loss:.4f}, CA~{ca_check:.1f}%, ASR~{asr_check:.1f}%")
            
            # Safety: if CA drops below 70%, abort
            if ca_check < 70:
                log.info(f"  ABORT: CA dropped too low. Restoring.")
                model.load_state_dict(initial_sd)
                return False
    
    return True


def subspace_reset_v2(model, masks, device, strategy="zero_top", noise_scale=0.05, reset_ratio=0.3):
    """Step 3: Aggressive subspace reset.
    
    Strategies:
    - 'zero_top': Zero out the top reset_ratio of masked parameters (by magnitude)
    - 'noise': Add large noise to masked parameters
    - 'shrink': Shrink masked parameters toward zero
    """
    log.info(f"=== Step 3: Subspace Reset (strategy={strategy}, ratio={reset_ratio}) ===")
    
    with torch.no_grad():
        if strategy == "zero_top":
            # Collect all masked param values
            all_masked_vals = []
            for name, p in model.named_parameters():
                if name in masks:
                    masked_vals = (p.abs() * masks[name]).flatten()
                    all_masked_vals.append(masked_vals[masked_vals > 0])
            
            all_masked_vals = torch.cat(all_masked_vals)
            if len(all_masked_vals) > 0:
                reset_threshold = torch.quantile(all_masked_vals, 1.0 - reset_ratio)
                total_reset = 0
                for name, p in model.named_parameters():
                    if name in masks:
                        reset_mask = (p.abs() >= reset_threshold) & (masks[name] > 0)
                        p.data[reset_mask] = 0.0
                        total_reset += reset_mask.sum().item()
                log.info(f"  Zeroed {total_reset} parameters (top {reset_ratio*100:.0f}% by magnitude)")
        
        elif strategy == "noise":
            total_reset = 0
            for name, p in model.named_parameters():
                if name in masks:
                    noise = torch.randn_like(p) * noise_scale
                    p.add_(noise * masks[name])
                    total_reset += (masks[name] > 0).sum().item()
            log.info(f"  Added noise (scale={noise_scale}) to {total_reset} parameters")
        
        elif strategy == "shrink":
            total_reset = 0
            shrink_factor = 1.0 - reset_ratio
            for name, p in model.named_parameters():
                if name in masks:
                    p.data = p.data * (1 - masks[name] * (1 - shrink_factor))
                    total_reset += (masks[name] > 0).sum().item()
            log.info(f"  Shrunk {total_reset} parameters by factor {shrink_factor:.2f}")


def backdoor_unlearning(model, def_loader, device, target_label=0,
                        epochs=20, lr=0.005, masks=None):
    """Step 4: Direct Backdoor Unlearning (replaces anti-rebound).
    
    Core idea: Simultaneously:
    1. Maintain clean accuracy (standard CE on clean data)
    2. MAXIMIZE loss when triggered inputs are classified as target
       (i.e., make the model FORGET the backdoor mapping)
    
    This is more direct than the entropy-based approach in v1.
    """
    log.info(f"=== Step 4: Backdoor Unlearning ({epochs} epochs, lr={lr}) ===")
    model.train()
    criterion = nn.CrossEntropyLoss()
    optimizer = optim.SGD(model.parameters(), lr=lr, momentum=0.9, weight_decay=5e-4)
    
    for epoch in range(epochs):
        total_loss = 0
        for images, labels in def_loader:
            images, labels = images.to(device), labels.to(device)
            optimizer.zero_grad()
            
            # L_clean: maintain clean accuracy
            outputs_clean = model(images)
            loss_clean = criterion(outputs_clean, labels)
            
            # L_unlearn: maximize loss for triggered->target mapping
            triggered = add_trigger_to_images(images)
            outputs_triggered = model(triggered)
            target_labels = torch.full_like(labels, target_label)
            loss_backdoor = criterion(outputs_triggered, target_labels)
            
            # Combined: minimize clean loss, MAXIMIZE backdoor loss
            # loss = L_clean - lambda * L_backdoor
            loss = loss_clean - 0.5 * loss_backdoor
            
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
            optimizer.step()
            total_loss += loss.item()
        
        if (epoch + 1) % 5 == 0 or epoch == 0:
            ca, asr = evaluate(model, [next(iter(def_loader))], device)
            log.info(f"  [Unlearn] Epoch {epoch+1}/{epochs}: loss={total_loss/len(def_loader):.4f}, CA~{ca:.1f}%, ASR~{asr:.1f}%")
            
            # Safety: stop if CA drops too much
            if ca < 60:
                log.info(f"  ABORT: CA too low ({ca:.1f}%). Stopping unlearning.")
                break
    
    log.info(f"  Unlearning complete.")

# ============================================================
# Main: Run multiple defense configurations
# ============================================================
def run_defense_config(attack_sd, def_loader, test_loader, device, config, config_name):
    """Run a single defense configuration and return results."""
    log.info(f"\n{'='*60}")
    log.info(f"Config: {config_name}")
    log.info(f"Params: {config}")
    log.info(f"{'='*60}")
    
    model = ResNet18(num_classes=10).to(device)
    model.load_state_dict(attack_sd)
    
    ca_before, asr_before = evaluate(model, test_loader, device)
    log.info(f"Before defense: CA={ca_before:.2f}%, ASR={asr_before:.2f}%")
    
    results = {"before": {"CA": ca_before, "ASR": asr_before}}
    
    # Step 1: Subspace identification
    masks = identify_backdoor_subspace(
        model, def_loader, device, top_ratio=config.get("top_ratio", 0.1))
    
    # Step 2: Sharpness ascent (optional)
    if config.get("do_sharpness", True):
        success = sharpness_ascent_v2(
            model, def_loader, masks, device,
            n_steps=config.get("ascent_steps", 30),
            ascent_eps=config.get("ascent_eps", 0.01),
            ascent_lr=config.get("ascent_lr", 0.003),
            max_grad_norm=config.get("max_grad_norm", 1.0))
        ca_s2, asr_s2 = evaluate(model, test_loader, device)
        log.info(f"After Step 2: CA={ca_s2:.2f}%, ASR={asr_s2:.2f}%")
        results["step2"] = {"CA": ca_s2, "ASR": asr_s2, "success": success}
    
    # Step 3: Subspace reset
    if config.get("do_reset", True):
        subspace_reset_v2(
            model, masks, device,
            strategy=config.get("reset_strategy", "shrink"),
            noise_scale=config.get("noise_scale", 0.05),
            reset_ratio=config.get("reset_ratio", 0.3))
        ca_s3, asr_s3 = evaluate(model, test_loader, device)
        log.info(f"After Step 3: CA={ca_s3:.2f}%, ASR={asr_s3:.2f}%")
        results["step3"] = {"CA": ca_s3, "ASR": asr_s3}
    
    # Step 4: Backdoor unlearning
    if config.get("do_unlearn", True):
        backdoor_unlearning(
            model, def_loader, device,
            epochs=config.get("unlearn_epochs", 20),
            lr=config.get("unlearn_lr", 0.005),
            masks=masks)
        ca_s4, asr_s4 = evaluate(model, test_loader, device)
        log.info(f"After Step 4: CA={ca_s4:.2f}%, ASR={asr_s4:.2f}%")
        results["step4"] = {"CA": ca_s4, "ASR": asr_s4}
    
    # Final: Standard FT to see if defense helped
    ft_results = standard_ft_defense(model, def_loader, 30, 0.005, device, test_loader, label=f"{config_name}-FT")
    ca_final, asr_final = ft_results[-1]
    log.info(f"After FT: CA={ca_final:.2f}%, ASR={asr_final:.2f}%")
    results["after_ft"] = {"CA": ca_final, "ASR": asr_final}
    results["ft_trajectory"] = ft_results
    
    return results


def main():
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    log.info(f"Device: {device}")
    log.info(f"BasinBreaker v2 - Hyperparameter Sweep")
    
    DATA_ROOT = "/root/workspace/aaai-backdoor/datasets/"
    
    # Load or train attack model
    attack_model_path = os.path.join(LOG_DIR, "sam_attack_model_20260511_150527.pt")
    
    d0_loader, def_loader, test_loader = prepare_data(DATA_ROOT)
    
    if os.path.exists(attack_model_path):
        log.info(f"Loading attack model from {attack_model_path}")
        attack_sd = torch.load(attack_model_path, map_location=device)
        model_check = ResNet18(num_classes=10).to(device)
        model_check.load_state_dict(attack_sd)
        ca, asr = evaluate(model_check, test_loader, device)
        log.info(f"Attack model: CA={ca:.2f}%, ASR={asr:.2f}%")
        del model_check
    else:
        log.info("Training attack model from scratch...")
        model = ResNet18(num_classes=10).to(device)
        torch.manual_seed(42)
        model.apply(lambda m: m.reset_parameters() if hasattr(m, "reset_parameters") else None)
        train_sam_attack(model, d0_loader, 100, 0.01, 0.05, device, test_loader)
        attack_sd = copy.deepcopy(model.state_dict())
        torch.save(attack_sd, os.path.join(LOG_DIR, f"sam_attack_model_{TIMESTAMP}.pt"))
        del model
    
    # Define configurations to test
    configs = {
        # Config A: Full pipeline with shrink reset
        "A_full_shrink": {
            "top_ratio": 0.1,
            "do_sharpness": True,
            "ascent_steps": 30,
            "ascent_eps": 0.01,
            "ascent_lr": 0.003,
            "max_grad_norm": 1.0,
            "do_reset": True,
            "reset_strategy": "shrink",
            "reset_ratio": 0.5,
            "do_unlearn": True,
            "unlearn_epochs": 20,
            "unlearn_lr": 0.005,
        },
        # Config B: Skip sharpness, aggressive reset + unlearning
        "B_reset_unlearn": {
            "top_ratio": 0.15,
            "do_sharpness": False,
            "do_reset": True,
            "reset_strategy": "shrink",
            "reset_ratio": 0.7,
            "do_unlearn": True,
            "unlearn_epochs": 30,
            "unlearn_lr": 0.01,
        },
        # Config C: Zero-out top params + unlearning
        "C_zero_unlearn": {
            "top_ratio": 0.15,
            "do_sharpness": False,
            "do_reset": True,
            "reset_strategy": "zero_top",
            "reset_ratio": 0.5,
            "do_unlearn": True,
            "unlearn_epochs": 20,
            "unlearn_lr": 0.005,
        },
        # Config D: Only unlearning (no structural changes)
        "D_unlearn_only": {
            "top_ratio": 0.1,
            "do_sharpness": False,
            "do_reset": False,
            "do_unlearn": True,
            "unlearn_epochs": 50,
            "unlearn_lr": 0.01,
        },
        # Config E: Aggressive sharpness + zero reset
        "E_sharp_zero": {
            "top_ratio": 0.2,
            "do_sharpness": True,
            "ascent_steps": 50,
            "ascent_eps": 0.02,
            "ascent_lr": 0.005,
            "max_grad_norm": 2.0,
            "do_reset": True,
            "reset_strategy": "zero_top",
            "reset_ratio": 0.3,
            "do_unlearn": True,
            "unlearn_epochs": 20,
            "unlearn_lr": 0.005,
        },
    }
    
    # Run all configs
    all_results = {}
    for config_name, config in configs.items():
        try:
            results = run_defense_config(attack_sd, def_loader, test_loader, device, config, config_name)
            all_results[config_name] = results
        except Exception as e:
            log.info(f"Config {config_name} FAILED: {e}")
            all_results[config_name] = {"error": str(e)}
    
    # Summary
    log.info("\n" + "="*60)
    log.info("FINAL COMPARISON")
    log.info("="*60)
    log.info(f"{'Config':<25} {'Before ASR':<12} {'After BB ASR':<14} {'After FT ASR':<14} {'Final CA':<10}")
    log.info("-" * 75)
    
    for name, res in all_results.items():
        if "error" in res:
            log.info(f"{name:<25} ERROR: {res['error']}")
            continue
        before_asr = res["before"]["ASR"]
        # Get the last step before FT
        last_step = "step4" if "step4" in res else ("step3" if "step3" in res else "step2")
        after_bb_asr = res.get(last_step, res["before"])["ASR"]
        after_ft_asr = res["after_ft"]["ASR"]
        final_ca = res["after_ft"]["CA"]
        log.info(f"{name:<25} {before_asr:<12.2f} {after_bb_asr:<14.2f} {after_ft_asr:<14.2f} {final_ca:<10.2f}")
    
    log.info(f"\nReference: Standard FT only -> ASR ~92.96%")
    
    # Save
    results_path = os.path.join(LOG_DIR, f"results_v2_{TIMESTAMP}.json")
    with open(results_path, "w") as f:
        json.dump(all_results, f, indent=2)
    log.info(f"Results saved to: {results_path}")


if __name__ == "__main__":
    main()
