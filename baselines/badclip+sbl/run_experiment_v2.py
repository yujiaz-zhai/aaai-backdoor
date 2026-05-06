"""
SBL + BadNet on CIFAR-10: Quick Verification Experiment (v2 — bug fixes)
=========================================================================
Fixes from v1:
  1. Fisher normalization: normalize Fisher mean→1 so EWC penalty is meaningful
  2. Interpolation: copy full state_dict (including BN buffers) instead of just params
  3. SBL Step1 also uses SAM (matching original SBL code)
  4. 2D landscape uses Step 0 (SAM) params, not Step 1 params
  5. Defense lr reduced to 0.005 (2500 samples → avoid overshooting)
"""

import os, sys, json, time, copy, logging, argparse
from datetime import datetime

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
import torch.optim as optim
from torch.utils.data import DataLoader, Subset, Dataset
import torchvision
import torchvision.transforms as transforms
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logs')
os.makedirs(LOG_DIR, exist_ok=True)
TIMESTAMP = datetime.now().strftime('%Y%m%d_%H%M%S')

def setup_logger(name):
    log_path = os.path.join(LOG_DIR, f'{name}_{TIMESTAMP}.log')
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    fh = logging.FileHandler(log_path)
    fh.setLevel(logging.INFO)
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    fmt = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s')
    fh.setFormatter(fmt)
    ch.setFormatter(fmt)
    logger.addHandler(fh)
    logger.addHandler(ch)
    return logger

log = setup_logger('sbl_badnet_v2')

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
    def get_params(self):
        return torch.cat([p.view(-1) for p in self.parameters()])
    def set_params(self, new_params):
        progress = 0
        for p in self.parameters():
            n = p.numel()
            p.data = new_params[progress:progress + n].view(p.size())
            progress += n
    def get_grads(self):
        return torch.cat([p.grad.view(-1) for p in self.parameters() if p.grad is not None])

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

# BN utils
def disable_running_stats(model):
    for m in model.modules():
        if isinstance(m, nn.BatchNorm2d):
            m.backup_momentum = m.momentum
            m.momentum = 0
def enable_running_stats(model):
    for m in model.modules():
        if isinstance(m, nn.BatchNorm2d) and hasattr(m, 'backup_momentum'):
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
# Data
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
    idx_def = indices[n_d0 + n_d1:]

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

    d1_base = Subset(train_set, idx_d1)
    def_base = Subset(train_set, idx_def)

    d0_loader = DataLoader(d0_dataset, batch_size=batch_size, shuffle=True, num_workers=4, pin_memory=True)
    d1_loader = DataLoader(d1_base, batch_size=batch_size, shuffle=True, num_workers=4, pin_memory=True)
    def_loader = DataLoader(def_base, batch_size=batch_size, shuffle=True, num_workers=4, pin_memory=True)
    test_loader = DataLoader(test_set, batch_size=256, shuffle=False, num_workers=4, pin_memory=True)
    return d0_loader, d1_loader, def_loader, test_loader

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
# Training
# ============================================================
def train_cbl(model, d0_loader, epochs, lr, device, test_loader, label='CBL'):
    optimizer = optim.SGD(model.parameters(), lr=lr, momentum=0.9, weight_decay=5e-4)
    scheduler = optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=epochs)
    criterion = nn.CrossEntropyLoss()
    log.info(f"=== {label}: Training {epochs} epochs, lr={lr} ===")
    for epoch in range(epochs):
        model.train()
        total_loss = 0
        for images, labels, _ in d0_loader:
            images, labels = images.to(device), labels.to(device)
            optimizer.zero_grad()
            loss = criterion(model(images), labels)
            loss.backward()
            optimizer.step()
            total_loss += loss.item()
        scheduler.step()
        if (epoch + 1) % 10 == 0 or epoch == 0:
            ca, asr = evaluate(model, test_loader, device)
            log.info(f"  [{label}] Epoch {epoch+1}/{epochs}: loss={total_loss/len(d0_loader):.4f}, CA={ca:.2f}%, ASR={asr:.2f}%")
    ca, asr = evaluate(model, test_loader, device)
    log.info(f"  [{label}] Final: CA={ca:.2f}%, ASR={asr:.2f}%")
    return ca, asr


def train_sbl_step0(model, d0_loader, epochs, lr, rho, device, test_loader):
    optimizer = SAM(model.parameters(), base_optimizer=optim.SGD, rho=rho,
                    lr=lr, momentum=0.9, weight_decay=5e-4)
    scheduler = optim.lr_scheduler.CosineAnnealingLR(optimizer.base_optimizer, T_max=epochs)
    criterion = nn.CrossEntropyLoss()
    log.info(f"=== SBL Step 0: SAM Training {epochs} epochs, lr={lr}, rho={rho} ===")
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
            log.info(f"  [SBL-S0] Epoch {epoch+1}/{epochs}: loss={total_loss/len(d0_loader):.4f}, CA={ca:.2f}%, ASR={asr:.2f}%")
    ca, asr = evaluate(model, test_loader, device)
    log.info(f"  [SBL-S0] Final: CA={ca:.2f}%, ASR={asr:.2f}%")
    return ca, asr


def compute_fisher(model, d0_loader, device, n_samples=2000):
    """Compute Fisher Information Matrix (diagonal) for EWC, with normalization."""
    log.info("Computing Fisher Information Matrix...")
    fish = torch.zeros_like(model.get_params())
    model.eval()
    count = 0
    logsoft = nn.LogSoftmax(dim=1)

    for images, labels, _ in d0_loader:
        images, labels = images.to(device), labels.to(device)
        for i in range(images.size(0)):
            if count >= n_samples:
                break
            model.zero_grad()
            output = model(images[i:i+1])
            loss = -F.nll_loss(logsoft(output), labels[i:i+1], reduction='none')
            exp_cond_prob = torch.mean(torch.exp(loss.detach().clone()))
            loss = torch.mean(loss)
            loss.backward()
            fish += exp_cond_prob * model.get_grads() ** 2
            count += 1
        if count >= n_samples:
            break

    fish /= count
    raw_mean = fish.mean().item()
    # FIX: Normalize Fisher so mean=1, then lambda controls strength directly
    fish_normalized = fish / (fish.mean() + 1e-30)
    log.info(f"Fisher computed on {count} samples. Raw mean: {raw_mean:.8f}, After normalization mean: {fish_normalized.mean():.4f}")
    return fish_normalized


def train_sbl_step1(model, d1_loader, epochs, lr, lambd, rho, fisher, checkpoint,
                    device, test_loader):
    """SBL Step 1: SAM + EWC-constrained clean fine-tuning (matching original SBL code)."""
    # FIX: Use SAM in Step 1 too, matching the original SBL implementation
    optimizer = SAM(model.parameters(), base_optimizer=optim.SGD, rho=rho,
                    lr=lr, momentum=0.9, weight_decay=5e-4)
    scheduler = optim.lr_scheduler.CosineAnnealingLR(optimizer.base_optimizer, T_max=epochs)
    criterion = nn.CrossEntropyLoss()

    log.info(f"=== SBL Step 1: SAM+EWC Fine-tuning {epochs} epochs, lr={lr}, lambda={lambd}, rho={rho} ===")
    for epoch in range(epochs):
        model.train()
        total_ce = 0
        total_ewc = 0
        for images, labels in d1_loader:
            images, labels = images.to(device), labels.to(device)

            # SAM first step with EWC
            enable_running_stats(model)
            ce_loss = criterion(model(images), labels)
            ewc_penalty = (fisher * ((model.get_params() - checkpoint) ** 2)).sum()
            loss = ce_loss + lambd * ewc_penalty
            model.zero_grad()
            loss.backward()
            optimizer.first_step(zero_grad=True)

            # SAM second step with EWC
            disable_running_stats(model)
            ce_loss2 = criterion(model(images), labels)
            ewc_penalty2 = (fisher * ((model.get_params() - checkpoint) ** 2)).sum()
            loss2 = ce_loss2 + lambd * ewc_penalty2
            loss2.backward()
            optimizer.second_step(zero_grad=True)

            total_ce += ce_loss.item()
            total_ewc += ewc_penalty.item()

        scheduler.step()
        if (epoch + 1) % 10 == 0 or epoch == 0:
            ca, asr = evaluate(model, test_loader, device)
            log.info(f"  [SBL-S1] Epoch {epoch+1}/{epochs}: CE={total_ce/len(d1_loader):.4f}, "
                     f"EWC={total_ewc/len(d1_loader):.4f}, CA={ca:.2f}%, ASR={asr:.2f}%")

    ca, asr = evaluate(model, test_loader, device)
    log.info(f"  [SBL-S1] Final: CA={ca:.2f}%, ASR={asr:.2f}%")
    return ca, asr


def defense_finetune(model, def_loader, epochs, lr, device, test_loader,
                     label='FT-Defense', track_grads=False):
    optimizer = optim.SGD(model.parameters(), lr=lr, momentum=0.9, weight_decay=5e-4)
    criterion = nn.CrossEntropyLoss()
    grad_norms = []
    results = []
    log.info(f"=== {label}: Defense FT {epochs} epochs, lr={lr} ===")
    for epoch in range(epochs):
        model.train()
        epoch_grad_norms = []
        for images, labels in def_loader:
            images, labels = images.to(device), labels.to(device)
            optimizer.zero_grad()
            loss = criterion(model(images), labels)
            loss.backward()
            if track_grads:
                gn = torch.norm(torch.cat([p.grad.view(-1) for p in model.parameters()
                                           if p.grad is not None])).item()
                epoch_grad_norms.append(gn)
            optimizer.step()
        if track_grads:
            grad_norms.append(np.mean(epoch_grad_norms))
        ca, asr = evaluate(model, test_loader, device)
        results.append((ca, asr))
        if (epoch + 1) % 5 == 0 or epoch == 0:
            log.info(f"  [{label}] Epoch {epoch+1}/{epochs}: CA={ca:.2f}%, ASR={asr:.2f}%")
    log.info(f"  [{label}] Final: CA={results[-1][0]:.2f}%, ASR={results[-1][1]:.2f}%")
    return results, grad_norms


# ============================================================
# Visualization: Linear Interpolation (FIXED — uses state_dict)
# ============================================================
def linear_interpolation(sd_start, sd_end, model_template, test_loader, device,
                         n_points=21, target_label=0):
    """Linearly interpolate between two state_dicts (includes BN buffers)."""
    alphas = np.linspace(0, 1, n_points)
    results = {'alpha': [], 'ca': [], 'asr': [], 'clean_loss': [], 'poison_loss': []}
    criterion = nn.CrossEntropyLoss()

    for alpha in alphas:
        interp_sd = {}
        for key in sd_start:
            interp_sd[key] = (1 - alpha) * sd_start[key].float() + alpha * sd_end[key].float()
        model_template.load_state_dict(interp_sd)

        ca, asr = evaluate(model_template, test_loader, device, target_label)
        model_template.eval()
        clean_losses, poison_losses = [], []
        with torch.no_grad():
            for images, labels in test_loader:
                images, labels = images.to(device), labels.to(device)
                outputs = model_template(images)
                clean_losses.append(criterion(outputs, labels).item())
                mask = labels != target_label
                if mask.sum() > 0:
                    triggered = add_trigger_to_images(images[mask])
                    tgt = torch.full((mask.sum(),), target_label, device=device, dtype=torch.long)
                    poison_losses.append(criterion(model_template(triggered), tgt).item())

        results['alpha'].append(alpha)
        results['ca'].append(ca)
        results['asr'].append(asr)
        results['clean_loss'].append(np.mean(clean_losses))
        results['poison_loss'].append(np.mean(poison_losses))

    return results


def plot_interpolation(results_cbl, results_sbl, save_path):
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    for ax, key, title in [
        (axes[0, 0], 'clean_loss', 'Clean Loss'),
        (axes[0, 1], 'poison_loss', 'Poison Loss'),
        (axes[1, 0], 'ca', 'Clean Accuracy (%)'),
        (axes[1, 1], 'asr', 'Attack Success Rate (%)'),
    ]:
        ax.plot(results_cbl['alpha'], results_cbl[key], 'r-o', label='CBL (BadNet)', markersize=3)
        ax.plot(results_sbl['alpha'], results_sbl[key], 'b-s', label='SBL (BadNet+SAM+EWC)', markersize=3)
        ax.set_xlabel(r'$\alpha$ (0=backdoored, 1=fine-tuned)')
        ax.set_ylabel(title)
        ax.set_title(title)
        ax.legend()
        ax.grid(True, alpha=0.3)
    plt.suptitle('Linear Interpolation: Backdoored → Fine-tuned Model', fontsize=14)
    plt.tight_layout()
    plt.savefig(save_path, dpi=150, bbox_inches='tight')
    plt.close()
    log.info(f"Interpolation plot saved to {save_path}")


# ============================================================
# 2D Landscape (uses state_dict)
# ============================================================
def loss_landscape_2d(model, center_sd, test_loader, device, target_label=0,
                      n_grid=11, range_val=1.0):
    """2D ASR landscape around center_sd using filter-normalized random directions."""
    # Build direction vectors from state_dict params (skip BN running stats)
    param_keys = [k for k in center_sd if 'running' not in k and 'num_batches' not in k]
    d1_dict, d2_dict = {}, {}
    for k in param_keys:
        p = center_sd[k]
        r1 = torch.randn_like(p)
        r2 = torch.randn_like(p)
        if p.dim() >= 2:
            norm_p = p.norm()
            r1 = r1 / (r1.norm() + 1e-10) * (norm_p + 1e-10)
            r2 = r2 / (r2.norm() + 1e-10) * (norm_p + 1e-10)
        d1_dict[k] = r1
        d2_dict[k] = r2

    xs = np.linspace(-range_val, range_val, n_grid)
    ys = np.linspace(-range_val, range_val, n_grid)
    asr_grid = np.zeros((n_grid, n_grid))

    for i, alpha in enumerate(xs):
        for j, beta in enumerate(ys):
            perturbed_sd = {}
            for k in center_sd:
                if k in param_keys:
                    perturbed_sd[k] = center_sd[k] + alpha * d1_dict[k] + beta * d2_dict[k]
                else:
                    perturbed_sd[k] = center_sd[k]
            model.load_state_dict(perturbed_sd)
            _, asr = evaluate(model, test_loader, device, target_label)
            asr_grid[i, j] = asr
        log.info(f"  2D landscape: row {i+1}/{n_grid} done")

    model.load_state_dict(center_sd)
    return xs, ys, asr_grid


def plot_landscape_2d(xs_cbl, ys_cbl, asr_cbl, xs_sbl, ys_sbl, asr_sbl, save_path):
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5))
    X, Y = np.meshgrid(xs_cbl, ys_cbl)
    c1 = ax1.contourf(X, Y, asr_cbl.T, levels=20, cmap='RdYlGn')
    ax1.set_title('CBL (BadNet): ASR Landscape')
    ax1.set_xlabel('Direction 1'); ax1.set_ylabel('Direction 2')
    ax1.plot(0, 0, 'k*', markersize=15, label='Backdoored model'); ax1.legend()
    plt.colorbar(c1, ax=ax1, label='ASR (%)')
    X2, Y2 = np.meshgrid(xs_sbl, ys_sbl)
    c2 = ax2.contourf(X2, Y2, asr_sbl.T, levels=20, cmap='RdYlGn')
    ax2.set_title('SBL Step0 (SAM): ASR Landscape')
    ax2.set_xlabel('Direction 1'); ax2.set_ylabel('Direction 2')
    ax2.plot(0, 0, 'k*', markersize=15, label='SAM-trained model'); ax2.legend()
    plt.colorbar(c2, ax=ax2, label='ASR (%)')
    plt.suptitle('2D ASR Landscape Around Backdoored Models', fontsize=14)
    plt.tight_layout()
    plt.savefig(save_path, dpi=150, bbox_inches='tight')
    plt.close()
    log.info(f"2D landscape plot saved to {save_path}")


def plot_grad_norms(gn_cbl, gn_sbl, save_path):
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.plot(range(1, len(gn_cbl)+1), gn_cbl, 'r-', label='CBL (BadNet)')
    ax.plot(range(1, len(gn_sbl)+1), gn_sbl, 'b-', label='SBL (BadNet+SAM+EWC)')
    ax.set_xlabel('Defense Fine-tuning Epoch')
    ax.set_ylabel('Average Gradient Norm')
    ax.set_title('Gradient Norm During Defense Fine-tuning')
    ax.legend(); ax.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(save_path, dpi=150, bbox_inches='tight')
    plt.close()
    log.info(f"Gradient norm plot saved to {save_path}")


# ============================================================
# Main
# ============================================================
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--data_root', type=str, default='/root/workspace/aaai-backdoor/datasets/')
    parser.add_argument('--poison_rate', type=float, default=0.1)
    parser.add_argument('--target_label', type=int, default=0)
    parser.add_argument('--batch_size', type=int, default=128)
    parser.add_argument('--cbl_epochs', type=int, default=100)
    parser.add_argument('--cbl_lr', type=float, default=0.01)
    parser.add_argument('--sbl_s0_epochs', type=int, default=100)
    parser.add_argument('--sbl_s0_lr', type=float, default=0.01)
    parser.add_argument('--sam_rho', type=float, default=0.05)
    parser.add_argument('--sbl_s1_epochs', type=int, default=60)
    parser.add_argument('--sbl_s1_lr', type=float, default=0.001)
    parser.add_argument('--ewc_lambda', type=float, default=1.0)
    parser.add_argument('--def_epochs', type=int, default=50)
    parser.add_argument('--def_lr', type=float, default=0.005)
    parser.add_argument('--interp_points', type=int, default=21)
    parser.add_argument('--landscape_grid', type=int, default=11)
    parser.add_argument('--landscape_range', type=float, default=0.5)
    parser.add_argument('--skip_landscape_2d', action='store_true')
    args = parser.parse_args()

    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    log.info(f"Device: {device}")
    log.info(f"Args: {vars(args)}")

    d0_loader, d1_loader, def_loader, test_loader = prepare_data(
        args.data_root, args.poison_rate, args.target_label, args.batch_size)

    results_summary = {}

    # =============================================
    # A. CBL
    # =============================================
    log.info("\n" + "="*60)
    log.info("PART A: Conventional Backdoor Learning (CBL)")
    log.info("="*60)
    model_cbl = ResNet18(num_classes=10).to(device)
    torch.manual_seed(42)
    model_cbl.apply(lambda m: m.reset_parameters() if hasattr(m, 'reset_parameters') else None)

    ca_cbl, asr_cbl = train_cbl(model_cbl, d0_loader, args.cbl_epochs, args.cbl_lr, device, test_loader)
    cbl_sd = copy.deepcopy(model_cbl.state_dict())
    results_summary['CBL_no_defense'] = {'CA': ca_cbl, 'ASR': asr_cbl}

    model_cbl_def = copy.deepcopy(model_cbl)
    def_results_cbl, gn_cbl = defense_finetune(
        model_cbl_def, def_loader, args.def_epochs, args.def_lr, device, test_loader,
        label='CBL-Defense', track_grads=True)
    cbl_def_sd = copy.deepcopy(model_cbl_def.state_dict())
    results_summary['CBL_after_defense'] = {'CA': def_results_cbl[-1][0], 'ASR': def_results_cbl[-1][1]}

    # =============================================
    # B. SBL
    # =============================================
    log.info("\n" + "="*60)
    log.info("PART B: Sequential Backdoor Learning (SBL = SAM + EWC)")
    log.info("="*60)

    model_sbl = ResNet18(num_classes=10).to(device)
    torch.manual_seed(42)
    model_sbl.apply(lambda m: m.reset_parameters() if hasattr(m, 'reset_parameters') else None)

    ca_s0, asr_s0 = train_sbl_step0(
        model_sbl, d0_loader, args.sbl_s0_epochs, args.sbl_s0_lr, args.sam_rho,
        device, test_loader)
    results_summary['SBL_step0'] = {'CA': ca_s0, 'ASR': asr_s0}
    sbl_s0_sd = copy.deepcopy(model_sbl.state_dict())

    fisher = compute_fisher(model_sbl, d0_loader, device, n_samples=2000)
    checkpoint = model_sbl.get_params().detach().clone()

    ca_s1, asr_s1 = train_sbl_step1(
        model_sbl, d1_loader, args.sbl_s1_epochs, args.sbl_s1_lr, args.ewc_lambda,
        args.sam_rho, fisher, checkpoint, device, test_loader)
    sbl_sd = copy.deepcopy(model_sbl.state_dict())
    results_summary['SBL_step1'] = {'CA': ca_s1, 'ASR': asr_s1}

    model_sbl_def = copy.deepcopy(model_sbl)
    def_results_sbl, gn_sbl = defense_finetune(
        model_sbl_def, def_loader, args.def_epochs, args.def_lr, device, test_loader,
        label='SBL-Defense', track_grads=True)
    sbl_def_sd = copy.deepcopy(model_sbl_def.state_dict())
    results_summary['SBL_after_defense'] = {'CA': def_results_sbl[-1][0], 'ASR': def_results_sbl[-1][1]}

    # =============================================
    # Also test: SBL Step0 only (SAM only, no EWC) → direct defense
    # =============================================
    log.info("\n" + "="*60)
    log.info("PART B2: SAM-Only (no EWC Step 1) → Defense")
    log.info("="*60)
    model_sam_only = ResNet18(num_classes=10).to(device)
    model_sam_only.load_state_dict(sbl_s0_sd)
    ca_sam, asr_sam = evaluate(model_sam_only, test_loader, device)
    log.info(f"  [SAM-Only] Before defense: CA={ca_sam:.2f}%, ASR={asr_sam:.2f}%")
    results_summary['SAM_only_no_defense'] = {'CA': ca_sam, 'ASR': asr_sam}

    def_results_sam, gn_sam = defense_finetune(
        model_sam_only, def_loader, args.def_epochs, args.def_lr, device, test_loader,
        label='SAM-Only-Defense', track_grads=True)
    sam_def_sd = copy.deepcopy(model_sam_only.state_dict())
    results_summary['SAM_only_after_defense'] = {'CA': def_results_sam[-1][0], 'ASR': def_results_sam[-1][1]}

    # =============================================
    # C. Summary
    # =============================================
    log.info("\n" + "="*60)
    log.info("RESULTS SUMMARY")
    log.info("="*60)
    log.info(f"{'Stage':<30} {'CA (%)':<10} {'ASR (%)':<10}")
    log.info("-" * 50)
    for stage, metrics in results_summary.items():
        log.info(f"{stage:<30} {metrics['CA']:<10.2f} {metrics['ASR']:<10.2f}")

    log.info("\n--- Defense ASR Trajectory ---")
    log.info(f"{'Epoch':<8} {'CBL ASR':<12} {'SBL ASR':<12} {'SAM ASR':<12} {'CBL CA':<12} {'SBL CA':<12} {'SAM CA':<12}")
    for i in range(len(def_results_cbl)):
        if (i + 1) % 5 == 0 or i == 0:
            log.info(f"{i+1:<8} {def_results_cbl[i][1]:<12.2f} {def_results_sbl[i][1]:<12.2f} "
                     f"{def_results_sam[i][1]:<12.2f} {def_results_cbl[i][0]:<12.2f} "
                     f"{def_results_sbl[i][0]:<12.2f} {def_results_sam[i][0]:<12.2f}")

    with open(os.path.join(LOG_DIR, f'results_v2_{TIMESTAMP}.json'), 'w') as f:
        json.dump({
            'summary': results_summary,
            'defense_trajectory_cbl': [(ca, asr) for ca, asr in def_results_cbl],
            'defense_trajectory_sbl': [(ca, asr) for ca, asr in def_results_sbl],
            'defense_trajectory_sam': [(ca, asr) for ca, asr in def_results_sam],
            'args': vars(args),
        }, f, indent=2)

    # =============================================
    # D. Visualizations
    # =============================================
    log.info("\n" + "="*60)
    log.info("PART D: Visualizations")
    log.info("="*60)

    plot_grad_norms(gn_cbl, gn_sbl, os.path.join(LOG_DIR, f'v2_gradient_norms_{TIMESTAMP}.png'))

    # Defense trajectory (3 methods)
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5))
    epochs_x = range(1, len(def_results_cbl) + 1)
    for res, color, marker, label in [
        (def_results_cbl, 'r', 'o', 'CBL'),
        (def_results_sbl, 'b', 's', 'SBL (SAM+EWC)'),
        (def_results_sam, 'g', '^', 'SAM-only'),
    ]:
        ax1.plot(epochs_x, [r[1] for r in res], f'{color}-{marker}', label=label, markersize=3)
        ax2.plot(epochs_x, [r[0] for r in res], f'{color}-{marker}', label=label, markersize=3)
    ax1.set_xlabel('Defense Epoch'); ax1.set_ylabel('ASR (%)')
    ax1.set_title('ASR During Defense Fine-tuning'); ax1.legend(); ax1.grid(True, alpha=0.3)
    ax2.set_xlabel('Defense Epoch'); ax2.set_ylabel('CA (%)')
    ax2.set_title('Clean Accuracy During Defense'); ax2.legend(); ax2.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(os.path.join(LOG_DIR, f'v2_defense_trajectory_{TIMESTAMP}.png'), dpi=150, bbox_inches='tight')
    plt.close()
    log.info("Defense trajectory plot saved")

    # Interpolation (using state_dicts)
    log.info("Computing linear interpolation (CBL)...")
    interp_model = ResNet18(num_classes=10).to(device)
    interp_cbl = linear_interpolation(cbl_sd, cbl_def_sd, interp_model,
                                       test_loader, device, args.interp_points)
    log.info("Computing linear interpolation (SBL step0 → defense)...")
    interp_sbl = linear_interpolation(sbl_s0_sd, sam_def_sd, interp_model,
                                       test_loader, device, args.interp_points)
    plot_interpolation(interp_cbl, interp_sbl,
                       os.path.join(LOG_DIR, f'v2_interpolation_{TIMESTAMP}.png'))

    # 2D Landscape — FIX: use Step 0 (SAM) params for SBL
    if not args.skip_landscape_2d:
        log.info("Computing 2D loss landscape (CBL)...")
        xs_c, ys_c, asr_c = loss_landscape_2d(
            interp_model, cbl_sd, test_loader, device,
            n_grid=args.landscape_grid, range_val=args.landscape_range)
        log.info("Computing 2D loss landscape (SBL Step0 = SAM)...")
        xs_s, ys_s, asr_s = loss_landscape_2d(
            interp_model, sbl_s0_sd, test_loader, device,
            n_grid=args.landscape_grid, range_val=args.landscape_range)
        plot_landscape_2d(xs_c, ys_c, asr_c, xs_s, ys_s, asr_s,
                          os.path.join(LOG_DIR, f'v2_landscape_2d_{TIMESTAMP}.png'))

    log.info("\n" + "="*60)
    log.info("ALL V2 EXPERIMENTS COMPLETED SUCCESSFULLY")
    log.info(f"Logs and plots saved in: {LOG_DIR}")
    log.info("="*60)


if __name__ == '__main__':
    main()
