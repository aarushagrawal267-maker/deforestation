"""Sylva U-Net: an encoder-decoder segmentation network with skip connections.

Implemented from scratch in PyTorch (Ronneberger et al., 2015 design adapted for
multispectral Sentinel-2 input). Weights are randomly initialised and learned only
from this project's training data; no external pretrained model is used.
"""

from __future__ import annotations

import torch
import torch.nn.functional as F
from torch import nn


class DoubleConv(nn.Module):
    """(3x3 conv -> BatchNorm -> ReLU) x 2, padding keeps spatial size."""

    def __init__(self, in_ch: int, out_ch: int):
        super().__init__()
        self.block = nn.Sequential(
            nn.Conv2d(in_ch, out_ch, 3, padding=1, bias=False),
            nn.BatchNorm2d(out_ch),
            nn.ReLU(inplace=True),
            nn.Conv2d(out_ch, out_ch, 3, padding=1, bias=False),
            nn.BatchNorm2d(out_ch),
            nn.ReLU(inplace=True),
        )

    def forward(self, x):
        return self.block(x)


class Down(nn.Module):
    def __init__(self, in_ch: int, out_ch: int):
        super().__init__()
        self.pool = nn.MaxPool2d(2)
        self.conv = DoubleConv(in_ch, out_ch)

    def forward(self, x):
        return self.conv(self.pool(x))


class Up(nn.Module):
    """Upsample x2, concatenate the encoder skip connection, DoubleConv."""

    def __init__(self, in_ch: int, skip_ch: int, out_ch: int, mode: str = "bilinear"):
        super().__init__()
        if mode == "transpose":
            self.up = nn.ConvTranspose2d(in_ch, in_ch // 2, 2, stride=2)
        else:
            self.up = nn.Sequential(
                nn.Upsample(scale_factor=2, mode="bilinear", align_corners=False),
                nn.Conv2d(in_ch, in_ch // 2, 1),
            )
        self.conv = DoubleConv(in_ch // 2 + skip_ch, out_ch)

    def forward(self, x, skip):
        x = self.up(x)
        dy, dx = skip.shape[-2] - x.shape[-2], skip.shape[-1] - x.shape[-1]
        if dy or dx:  # handle odd input sizes
            x = F.pad(x, [dx // 2, dx - dx // 2, dy // 2, dy - dy // 2])
        return self.conv(torch.cat([skip, x], dim=1))


class UNet(nn.Module):
    def __init__(
        self,
        in_channels: int = 10,
        num_classes: int = 5,
        base: int = 32,
        depth: int = 4,
        dropout: float = 0.2,
        up_mode: str = "bilinear",
    ):
        super().__init__()
        self.config = dict(
            in_channels=in_channels,
            num_classes=num_classes,
            base=base,
            depth=depth,
            dropout=dropout,
            up_mode=up_mode,
        )
        chs = [base * 2**i for i in range(depth + 1)]  # e.g. 32,64,128,256,512
        self.inc = DoubleConv(in_channels, chs[0])
        self.downs = nn.ModuleList([Down(chs[i], chs[i + 1]) for i in range(depth)])
        self.drop = nn.Dropout2d(dropout) if dropout > 0 else nn.Identity()
        self.ups = nn.ModuleList([Up(chs[i + 1], chs[i], chs[i], up_mode) for i in reversed(range(depth))])
        self.head = nn.Conv2d(chs[0], num_classes, 1)
        self._init_weights()

    def _init_weights(self):
        for m in self.modules():
            if isinstance(m, nn.Conv2d | nn.ConvTranspose2d):
                nn.init.kaiming_normal_(m.weight, mode="fan_out", nonlinearity="relu")
                if m.bias is not None:
                    nn.init.zeros_(m.bias)
            elif isinstance(m, nn.BatchNorm2d):
                nn.init.ones_(m.weight)
                nn.init.zeros_(m.bias)

    def forward(self, x):
        skips = [self.inc(x)]
        for d in self.downs:
            skips.append(d(skips[-1]))
        x = self.drop(skips.pop())
        for up in self.ups:
            x = up(x, skips.pop())
        return self.head(x)


def count_parameters(model: nn.Module) -> int:
    return sum(p.numel() for p in model.parameters() if p.requires_grad)
