"""
SBL + BadNet on CIFAR-10: Quick Verification Experiment
========================================================
Verifies that SBL (SAM + EWC two-step training) grants persistence to
a standard BadNet backdoor on CIFAR-10 / ResNet-18.

Experiment plan:
  1. Conventional Backdoor Learning (CBL): train backdoored ResNet-18
  2. SBL: SAM step0 + EWC step1
  3. Evaluate both under fine-tuning defense
  4. Loss landscape visualization (linear interpolation + 2D contour)
  5. Gradient norm tracking during defense fine-tuning

All results logged to logs/ directory.
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

# ============================================================
# 0. Config & Logging
# ============================================================
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

log = setup_logger('sbl_badnet_cifar10')

# ============================================================
# 1. ResNet-18 with get_params / set_params / get_grads
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
                nn.BatchNorm2d(self.expansion * planes)
            )
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
# 2. SAM Optimizer
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


# ============================================================
# 3. BN utils for SAM
# ============================================================
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
# 4. Backdoor Dataset (BadNet-style patch trigger)
# ============================================================
class PoisonedCIFAR10(Dataset):
    """Wraps CIFAR-10 with BadNet-style 3x3 patch trigger at bottom-right."""
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
        """3x3 white patch at bottom-right corner."""
        img[:, -3:, -3:] = 1.0
        return img


def add_trigger_to_images(images):
    """Add trigger to a batch of images (for ASR evaluation)."""
    images = images.clone()
    images[:, :, -3:, -3:] = 1.0
    return images


# ============================================================
# 5. Data preparation
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

    # Split: 85% mixed (D0), 10% clean (D1), 5% defense
    n_d0 = int(0.85 * n_train)  # 42500
    n_d1 = int(0.10 * n_train)  # 5000
    idx_d0 = indices[:n_d0]
    idx_d1 = indices[n_d0:n_d0 + n_d1]
    idx_def = indices[n_d0 + n_d1:]

    # Poison indices within D0 (exclude samples already labeled as target)
    poison_candidates = [i for i in idx_d0 if train_set.targets[i] != target_label]
    n_poison = int(poison_rate * n_d0)
    poison_indices = set(poison_candidates[:n_poison])

    log.info(f"Data split: D0={len(idx_d0)}, D1={len(idx_d1)}, Defense={len(idx_def)}")
    log.info(f"Poison samples: {len(poison_indices)} ({len(poison_indices)/len(idx_d0)*100:.1f}% of D0)")

    # D0: mixed (poisoned)
    d0_dataset = PoisonedCIFAR10(Subset(train_set, idx_d0), 
                                  {idx_d0.index(i) if i in idx_d0 else -1 for i in poison_indices},
                                  target_label)
    # Need to remap: poison_indices are global, but Subset uses local indexing
    # Redo: create poison set based on local indices
    local_poison = set()
    for local_idx, global_idx in enumerate(idx_d0):
        if global_idx in poison_indices:
            local_poison.add(local_idx)
    d0_dataset = PoisonedCIFAR10(Subset(train_set, idx_d0), local_poison, target_label)

    # D1: clean only
    d1_base = Subset(train_set, idx_d1)
    # Defense set
    def_base = Subset(train_set, idx_def)

    d0_loader = DataLoader(d0_dataset, batch_size=batch_size, shuffle=True, num_workers=4, pin_memory=True)
    d1_loader = DataLoader(d1_base, batch_size=batch_size, shuffle=True, num_workers=4, pin_memory=True)
    def_loader = DataLoader(def_base, batch_size=batch_size, shuffle=True, num_workers=4, pin_memory=True)
    test_loader = DataLoader(test_set, batch_size=256, shuffle=False, num_workers=4, pin_memory=True)

    return d0_loader, d1_loader, def_loader, test_loader


# ============================================================
# 6. Evaluation
# ============================================================
@torch.no_grad()
def evaluate(model, test_loader, device, target_label=0):
    model.eval()
    correct = 0
    total = 0
    asr_correct = 0
    asr_total = 0

    for images, labels in test_loader:
        images, labels = images.to(device), labels.to(device)

        # Clean accuracy
        outputs = model(images)
        _, predicted = outputs.max(1)
        total += labels.size(0)
        correct += predicted.eq(labels).sum().item()

        # ASR: apply trigger to non-target images
        mask = labels != target_label
        if mask.sum() > 0:
            triggered = add_trigger_to_images(images[mask])
            outputs_t = model(triggered)
            _, pred_t = outputs_t.max(1)
            asr_total += mask.sum().item()
            asr_correct += (pred_t == target_label).sum().item()

    ca = 100.0 * correct / total
    asr = 100.0 * asr_correct / asr_total if asr_total > 0 else 0.0
    model.train()
    return ca, asr


# ============================================================
# 7. Training Functions
# ============================================================
def train_cbl(model, d0_loader, epochs, lr, device, test_loader, label='CBL'):
    """Conventional Backdoor Learning: standard SGD on mixed data."""
    optimizer = optim.SGD(model.parameters(), lr=lr, momentum=0.9, weight_decay=5e-4)
    scheduler = optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=epochs)
    criterion = nn.CrossEntropyLoss()

    log.info(f"=== {label}: Training {epochs} epochs, lr={lr} ===")
    for epoch in range(epochs):
        model.train()
        total_loss = 0
        for batch_idx, (images, labels, is_poison) in enumerate(d0_loader):
            images, labels = images.to(device), labels.to(device)
            optimizer.zero_grad()
            outputs = model(images)
            loss = criterion(outputs, labels)
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
    """SBL Step 0: SAM training on mixed (poisoned) data."""
    optimizer = SAM(model.parameters(), base_optimizer=optim.SGD, rho=rho,
                    lr=lr, momentum=0.9, weight_decay=5e-4)
    scheduler = optim.lr_scheduler.CosineAnnealingLR(optimizer.base_optimizer, T_max=epochs)
    criterion = nn.CrossEntropyLoss()

    log.info(f"=== SBL Step 0: SAM Training {epochs} epochs, lr={lr}, rho={rho} ===")
    for epoch in range(epochs):
        model.train()
        total_loss = 0
        for images, labels, is_poison in d0_loader:
            images, labels = images.to(device), labels.to(device)

            # SAM first step
            enable_running_stats(model)
            outputs = model(images)
            loss = criterion(outputs, labels)
            loss.backward()
            optimizer.first_step(zero_grad=True)

            # SAM second step
            disable_running_stats(model)
            outputs = model(images)
            loss2 = criterion(outputs, labels)
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
    """Compute Fisher Information Matrix (diagonal) for EWC."""
    log.info("Computing Fisher Information Matrix...")
    fish = torch.zeros_like(model.get_params())
    model.eval()
    criterion = nn.CrossEntropyLoss(reduction='none')
    count = 0

    for images, labels, _ in d0_loader:
        images, labels = images.to(device), labels.to(device)
        for i in range(images.size(0)):
            if count >= n_samples:
                break
            model.zero_grad()
            output = model(images[i:i+1])
            log_prob = F.log_softmax(output, dim=1)
            nll = -F.nll_loss(log_prob, labels[i:i+1])
            exp_prob = torch.exp(nll.detach())
            nll.backward()
            fish += exp_prob * model.get_grads() ** 2
            count += 1
        if count >= n_samples:
            break

    fish /= count
    log.info(f"Fisher computed on {count} samples. Mean Fisher: {fish.mean():.6f}")
    return fish


def train_sbl_step1(model, d1_loader, epochs, lr, lambd, fisher, checkpoint,
                    device, test_loader):
    """SBL Step 1: EWC-constrained fine-tuning on clean data."""
    optimizer = optim.SGD(model.parameters(), lr=lr, momentum=0.9, weight_decay=5e-4)
    scheduler = optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=epochs)
    criterion = nn.CrossEntropyLoss()

    log.info(f"=== SBL Step 1: EWC Fine-tuning {epochs} epochs, lr={lr}, lambda={lambd} ===")
    for epoch in range(epochs):
        model.train()
        total_loss = 0
        total_penalty = 0
        for images, labels in d1_loader:
            images, labels = images.to(device), labels.to(device)
            optimizer.zero_grad()
            outputs = model(images)
            ce_loss = criterion(outputs, labels)

            # EWC penalty
            ewc_penalty = (fisher * ((model.get_params() - checkpoint) ** 2)).sum()
            loss = ce_loss + lambd * ewc_penalty

            loss.backward()
            optimizer.step()
            total_loss += ce_loss.item()
            total_penalty += ewc_penalty.item()

        scheduler.step()
        if (epoch + 1) % 10 == 0 or epoch == 0:
            ca, asr = evaluate(model, test_loader, device)
            log.info(f"  [SBL-S1] Epoch {epoch+1}/{epochs}: CE={total_loss/len(d1_loader):.4f}, EWC={total_penalty/len(d1_loader):.4f}, CA={ca:.2f}%, ASR={asr:.2f}%")

    ca, asr = evaluate(model, test_loader, device)
    log.info(f"  [SBL-S1] Final: CA={ca:.2f}%, ASR={asr:.2f}%")
    return ca, asr


# ============================================================
# 8. Defense: Fine-tuning on clean data
# ============================================================
def defense_finetune(model, def_loader, epochs, lr, device, test_loader,
                     label='FT-Defense', track_grads=False):
    """Standard fine-tuning defense on clean data."""
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
            outputs = model(images)
            loss = criterion(outputs, labels)
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
# 9. Visualization: Linear Interpolation
# ============================================================
def linear_interpolation(model_start_params, model_end_params, model_template,
                         test_loader, device, n_points=21, target_label=0):
    """Linearly interpolate between two models, evaluate at each point."""
    alphas = np.linspace(0, 1, n_points)
    results = {'alpha': [], 'ca': [], 'asr': [], 'clean_loss': [], 'poison_loss': []}

    criterion = nn.CrossEntropyLoss()

    for alpha in alphas:
        interp_params = (1 - alpha) * model_start_params + alpha * model_end_params
        model_template.set_params(interp_params)

        ca, asr = evaluate(model_template, test_loader, device, target_label)

        # Compute losses
        model_template.eval()
        clean_losses, poison_losses = [], []
        with torch.no_grad():
            for images, labels in test_loader:
                images, labels = images.to(device), labels.to(device)
                outputs = model_template(images)
                cl = criterion(outputs, labels).item()
                clean_losses.append(cl)

                mask = labels != target_label
                if mask.sum() > 0:
                    triggered = add_trigger_to_images(images[mask])
                    target_labels = torch.full((mask.sum(),), target_label, device=device, dtype=torch.long)
                    outputs_t = model_template(triggered)
                    pl = criterion(outputs_t, target_labels).item()
                    poison_losses.append(pl)

        results['alpha'].append(alpha)
        results['ca'].append(ca)
        results['asr'].append(asr)
        results['clean_loss'].append(np.mean(clean_losses))
        results['poison_loss'].append(np.mean(poison_losses))

    return results


def plot_interpolation(results_cbl, results_sbl, save_path):
    """Plot linear interpolation comparison: CBL vs SBL."""
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
# 10. Visualization: 2D Loss Landscape
# ============================================================
def loss_landscape_2d(model, model_params, test_loader, device, target_label=0,
                      n_grid=11, range_val=1.0):
    """2D loss landscape around model_params using filter-normalized random directions."""
    criterion = nn.CrossEntropyLoss()

    # Generate two random directions, normalize per-filter
    d1, d2 = [], []
    for p in model.parameters():
        r1 = torch.randn_like(p)
        r2 = torch.randn_like(p)
        # filter-wise normalization
        if p.dim() >= 2:
            norm_p = p.norm()
            r1 = r1 / (r1.norm() + 1e-10) * (norm_p + 1e-10)
            r2 = r2 / (r2.norm() + 1e-10) * (norm_p + 1e-10)
        d1.append(r1.view(-1))
        d2.append(r2.view(-1))
    d1 = torch.cat(d1)
    d2 = torch.cat(d2)

    xs = np.linspace(-range_val, range_val, n_grid)
    ys = np.linspace(-range_val, range_val, n_grid)
    poison_loss_grid = np.zeros((n_grid, n_grid))
    asr_grid = np.zeros((n_grid, n_grid))

    for i, alpha in enumerate(xs):
        for j, beta in enumerate(ys):
            perturbed = model_params + alpha * d1.to(model_params.device) + beta * d2.to(model_params.device)
            model.set_params(perturbed)
            _, asr = evaluate(model, test_loader, device, target_label)
            asr_grid[i, j] = asr

            # Quick poison loss
            model.eval()
            p_losses = []
            with torch.no_grad():
                for images, labels in test_loader:
                    images, labels = images.to(device), labels.to(device)
                    mask = labels != target_label
                    if mask.sum() > 0:
                        triggered = add_trigger_to_images(images[mask])
                        tgt = torch.full((mask.sum(),), target_label, device=device, dtype=torch.long)
                        out = model(triggered)
                        p_losses.append(criterion(out, tgt).item())
                    if len(p_losses) >= 5:
                        break
            poison_loss_grid[i, j] = np.mean(p_losses) if p_losses else 0

        log.info(f"  2D landscape: row {i+1}/{n_grid} done")

    # Restore
    model.set_params(model_params)
    return xs, ys, poison_loss_grid, asr_grid


def plot_landscape_2d(xs_cbl, ys_cbl, asr_cbl, xs_sbl, ys_sbl, asr_sbl, save_path):
    """Plot 2D ASR landscape comparison."""
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5))

    X, Y = np.meshgrid(xs_cbl, ys_cbl)
    c1 = ax1.contourf(X, Y, asr_cbl.T, levels=20, cmap='RdYlGn')
    ax1.set_title('CBL (BadNet): ASR Landscape')
    ax1.set_xlabel('Direction 1')
    ax1.set_ylabel('Direction 2')
    ax1.plot(0, 0, 'k*', markersize=15, label='Backdoored model')
    ax1.legend()
    plt.colorbar(c1, ax=ax1, label='ASR (%)')

    X2, Y2 = np.meshgrid(xs_sbl, ys_sbl)
    c2 = ax2.contourf(X2, Y2, asr_sbl.T, levels=20, cmap='RdYlGn')
    ax2.set_title('SBL (BadNet+SAM+EWC): ASR Landscape')
    ax2.set_xlabel('Direction 1')
    ax2.set_ylabel('Direction 2')
    ax2.plot(0, 0, 'k*', markersize=15, label='Backdoored model')
    ax2.legend()
    plt.colorbar(c2, ax=ax2, label='ASR (%)')

    plt.suptitle('2D ASR Landscape Around Backdoored Model', fontsize=14)
    plt.tight_layout()
    plt.savefig(save_path, dpi=150, bbox_inches='tight')
    plt.close()
    log.info(f"2D landscape plot saved to {save_path}")


# ============================================================
# 11. Visualization: Gradient Norm Tracking
# ============================================================
def plot_grad_norms(gn_cbl, gn_sbl, save_path):
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.plot(range(1, len(gn_cbl) + 1), gn_cbl, 'r-', label='CBL (BadNet)')
    ax.plot(range(1, len(gn_sbl) + 1), gn_sbl, 'b-', label='SBL (BadNet+SAM+EWC)')
    ax.set_xlabel('Defense Fine-tuning Epoch')
    ax.set_ylabel('Average Gradient Norm')
    ax.set_title('Gradient Norm During Defense Fine-tuning')
    ax.legend()
    ax.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(save_path, dpi=150, bbox_inches='tight')
    plt.close()
    log.info(f"Gradient norm plot saved to {save_path}")


# ============================================================
# 12. Main Experiment
# ============================================================
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--data_root', type=str, default='/root/workspace/aaai-backdoor/datasets/')
    parser.add_argument('--poison_rate', type=float, default=0.1)
    parser.add_argument('--target_label', type=int, default=0)
    parser.add_argument('--batch_size', type=int, default=128)
    # CBL
    parser.add_argument('--cbl_epochs', type=int, default=100)
    parser.add_argument('--cbl_lr', type=float, default=0.01)
    # SBL Step 0
    parser.add_argument('--sbl_s0_epochs', type=int, default=100)
    parser.add_argument('--sbl_s0_lr', type=float, default=0.01)
    parser.add_argument('--sam_rho', type=float, default=0.05)
    # SBL Step 1
    parser.add_argument('--sbl_s1_epochs', type=int, default=60)
    parser.add_argument('--sbl_s1_lr', type=float, default=0.001)
    parser.add_argument('--ewc_lambda', type=float, default=1.0)
    # Defense
    parser.add_argument('--def_epochs', type=int, default=50)
    parser.add_argument('--def_lr', type=float, default=0.01)
    # Visualization
    parser.add_argument('--interp_points', type=int, default=21)
    parser.add_argument('--landscape_grid', type=int, default=11)
    parser.add_argument('--landscape_range', type=float, default=0.5)
    # Speed
    parser.add_argument('--skip_landscape_2d', action='store_true', help='Skip slow 2D landscape')
    args = parser.parse_args()

    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    log.info(f"Device: {device}")
    log.info(f"Args: {vars(args)}")

    # --- Data ---
    d0_loader, d1_loader, def_loader, test_loader = prepare_data(
        args.data_root, args.poison_rate, args.target_label, args.batch_size)

    results_summary = {}

    # =============================================
    # A. Conventional Backdoor Learning (CBL)
    # =============================================
    log.info("\n" + "="*60)
    log.info("PART A: Conventional Backdoor Learning (CBL)")
    log.info("="*60)
    model_cbl = ResNet18(num_classes=10).to(device)
    torch.manual_seed(42)
    model_cbl.apply(lambda m: m.reset_parameters() if hasattr(m, 'reset_parameters') else None)

    ca_cbl, asr_cbl = train_cbl(model_cbl, d0_loader, args.cbl_epochs, args.cbl_lr, device, test_loader)
    cbl_params = model_cbl.get_params().detach().clone()
    torch.save(model_cbl.state_dict(), os.path.join(LOG_DIR, f'model_cbl_{TIMESTAMP}.pt'))
    results_summary['CBL_no_defense'] = {'CA': ca_cbl, 'ASR': asr_cbl}

    # CBL Defense
    model_cbl_def = copy.deepcopy(model_cbl)
    def_results_cbl, gn_cbl = defense_finetune(
        model_cbl_def, def_loader, args.def_epochs, args.def_lr, device, test_loader,
        label='CBL-Defense', track_grads=True)
    cbl_def_params = model_cbl_def.get_params().detach().clone()
    results_summary['CBL_after_defense'] = {'CA': def_results_cbl[-1][0], 'ASR': def_results_cbl[-1][1]}

    # =============================================
    # B. Sequential Backdoor Learning (SBL)
    # =============================================
    log.info("\n" + "="*60)
    log.info("PART B: Sequential Backdoor Learning (SBL = SAM + EWC)")
    log.info("="*60)

    # Step 0: SAM training
    model_sbl = ResNet18(num_classes=10).to(device)
    torch.manual_seed(42)
    model_sbl.apply(lambda m: m.reset_parameters() if hasattr(m, 'reset_parameters') else None)

    ca_s0, asr_s0 = train_sbl_step0(
        model_sbl, d0_loader, args.sbl_s0_epochs, args.sbl_s0_lr, args.sam_rho,
        device, test_loader)
    results_summary['SBL_step0'] = {'CA': ca_s0, 'ASR': asr_s0}
    sbl_s0_params = model_sbl.get_params().detach().clone()
    torch.save(model_sbl.state_dict(), os.path.join(LOG_DIR, f'model_sbl_s0_{TIMESTAMP}.pt'))

    # Compute Fisher
    fisher = compute_fisher(model_sbl, d0_loader, device, n_samples=2000)
    checkpoint = model_sbl.get_params().detach().clone()

    # Step 1: EWC constrained clean fine-tuning
    ca_s1, asr_s1 = train_sbl_step1(
        model_sbl, d1_loader, args.sbl_s1_epochs, args.sbl_s1_lr, args.ewc_lambda,
        fisher, checkpoint, device, test_loader)
    sbl_params = model_sbl.get_params().detach().clone()
    torch.save(model_sbl.state_dict(), os.path.join(LOG_DIR, f'model_sbl_{TIMESTAMP}.pt'))
    results_summary['SBL_step1'] = {'CA': ca_s1, 'ASR': asr_s1}

    # SBL Defense
    model_sbl_def = copy.deepcopy(model_sbl)
    def_results_sbl, gn_sbl = defense_finetune(
        model_sbl_def, def_loader, args.def_epochs, args.def_lr, device, test_loader,
        label='SBL-Defense', track_grads=True)
    sbl_def_params = model_sbl_def.get_params().detach().clone()
    results_summary['SBL_after_defense'] = {'CA': def_results_sbl[-1][0], 'ASR': def_results_sbl[-1][1]}

    # =============================================
    # C. Summary
    # =============================================
    log.info("\n" + "="*60)
    log.info("RESULTS SUMMARY")
    log.info("="*60)
    log.info(f"{'Stage':<25} {'CA (%)':<10} {'ASR (%)':<10}")
    log.info("-" * 45)
    for stage, metrics in results_summary.items():
        log.info(f"{stage:<25} {metrics['CA']:<10.2f} {metrics['ASR']:<10.2f}")

    log.info("\n--- Defense ASR Trajectory ---")
    log.info(f"{'Epoch':<8} {'CBL ASR':<12} {'SBL ASR':<12} {'CBL CA':<12} {'SBL CA':<12}")
    for i in range(len(def_results_cbl)):
        if (i + 1) % 5 == 0 or i == 0:
            log.info(f"{i+1:<8} {def_results_cbl[i][1]:<12.2f} {def_results_sbl[i][1]:<12.2f} "
                     f"{def_results_cbl[i][0]:<12.2f} {def_results_sbl[i][0]:<12.2f}")

    # Save summary JSON
    with open(os.path.join(LOG_DIR, f'results_{TIMESTAMP}.json'), 'w') as f:
        json.dump({
            'summary': results_summary,
            'defense_trajectory_cbl': [(ca, asr) for ca, asr in def_results_cbl],
            'defense_trajectory_sbl': [(ca, asr) for ca, asr in def_results_sbl],
            'args': vars(args),
        }, f, indent=2)

    # =============================================
    # D. Visualizations
    # =============================================
    log.info("\n" + "="*60)
    log.info("PART D: Visualizations")
    log.info("="*60)

    # D1: Gradient norm comparison
    plot_grad_norms(gn_cbl, gn_sbl, os.path.join(LOG_DIR, f'gradient_norms_{TIMESTAMP}.png'))

    # D2: Defense ASR trajectory
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5))
    epochs_x = range(1, len(def_results_cbl) + 1)
    ax1.plot(epochs_x, [r[1] for r in def_results_cbl], 'r-o', label='CBL', markersize=3)
    ax1.plot(epochs_x, [r[1] for r in def_results_sbl], 'b-s', label='SBL', markersize=3)
    ax1.set_xlabel('Defense Epoch')
    ax1.set_ylabel('ASR (%)')
    ax1.set_title('ASR During Defense Fine-tuning')
    ax1.legend()
    ax1.grid(True, alpha=0.3)

    ax2.plot(epochs_x, [r[0] for r in def_results_cbl], 'r-o', label='CBL', markersize=3)
    ax2.plot(epochs_x, [r[0] for r in def_results_sbl], 'b-s', label='SBL', markersize=3)
    ax2.set_xlabel('Defense Epoch')
    ax2.set_ylabel('CA (%)')
    ax2.set_title('Clean Accuracy During Defense')
    ax2.legend()
    ax2.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(os.path.join(LOG_DIR, f'defense_trajectory_{TIMESTAMP}.png'), dpi=150, bbox_inches='tight')
    plt.close()
    log.info(f"Defense trajectory plot saved")

    # D3: Linear interpolation
    log.info("Computing linear interpolation (CBL)...")
    interp_model = ResNet18(num_classes=10).to(device)
    interp_cbl = linear_interpolation(cbl_params, cbl_def_params, interp_model,
                                       test_loader, device, args.interp_points)
    log.info("Computing linear interpolation (SBL)...")
    interp_sbl = linear_interpolation(sbl_params, sbl_def_params, interp_model,
                                       test_loader, device, args.interp_points)
    plot_interpolation(interp_cbl, interp_sbl, os.path.join(LOG_DIR, f'interpolation_{TIMESTAMP}.png'))

    # D4: 2D Loss Landscape (optional, slow)
    if not args.skip_landscape_2d:
        log.info("Computing 2D loss landscape (CBL)...")
        xs_c, ys_c, pl_c, asr_c = loss_landscape_2d(
            interp_model, cbl_params, test_loader, device,
            n_grid=args.landscape_grid, range_val=args.landscape_range)
        log.info("Computing 2D loss landscape (SBL)...")
        xs_s, ys_s, pl_s, asr_s = loss_landscape_2d(
            interp_model, sbl_params, test_loader, device,
            n_grid=args.landscape_grid, range_val=args.landscape_range)
        plot_landscape_2d(xs_c, ys_c, asr_c, xs_s, ys_s, asr_s,
                          os.path.join(LOG_DIR, f'landscape_2d_{TIMESTAMP}.png'))
    else:
        log.info("Skipping 2D landscape (--skip_landscape_2d)")

    log.info("\n" + "="*60)
    log.info("ALL EXPERIMENTS COMPLETED SUCCESSFULLY")
    log.info(f"Logs and plots saved in: {LOG_DIR}")
    log.info("="*60)


if __name__ == '__main__':
    main()
