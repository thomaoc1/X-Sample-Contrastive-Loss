import os
import time
import pandas as pd
from abc import abstractmethod
from datetime import datetime
import torch
from torch import nn, optim
from torch.cuda.amp import GradScaler, autocast
from torch.utils.data import DataLoader
from torchvision import transforms
from torchvision.datasets import ImageFolder

from src.pretraining.encoder import ResNetEncoder


class ClrTrainer:
    def __init__(
            self,
            dataset_path: str,
            batch_size: int,
            device: str,
            encoder_checkpoint_base_path: str,
            image_augmentation_transform: nn.Module | transforms.Compose,
            tau: float,
            head_out_features: int = 128,
            num_workers_dl: int = 8,
            epochs: int = 100,
            encoder_load_path: str | None = None,
            initial_transform: nn.Module | transforms.Compose | None = None,
    ):
        self._batch_size = batch_size
        self._device = device
        self._epochs = epochs
        self._image_augmentation_fn = image_augmentation_transform
        self._tau = tau
        self._init_checkpoint_dir(base_path=encoder_checkpoint_base_path)
        self._init_data_loader(path=dataset_path, initial_transform=initial_transform, num_workers=num_workers_dl)
        self._init_encoder(out_features=head_out_features, load_path=encoder_load_path)

    def _init_checkpoint_dir(self, base_path: str):
        now = datetime.now()
        dir_name = now.strftime("%b%d-%H:%M:%S")
        self._encoder_checkpoint_path = os.path.join(base_path, dir_name)
        if not os.path.exists(self._encoder_checkpoint_path):
            os.makedirs(self._encoder_checkpoint_path)

    def _init_encoder(self, out_features: int, load_path=None):
        self._image_encoder = ResNetEncoder(out_dim=out_features).to(self._device)
        if load_path:
            try:
                self._image_encoder.load_state_dict(
                    torch.load(f"{load_path}-image_encoder.pt", map_location=self._device)
                )
                print("Loaded pre-trained weights successfully.")
            except FileNotFoundError:
                print("No pre-trained weights found. Training from scratch.")

    def _init_data_loader(self, path: str, num_workers: int, initial_transform: nn.Module | transforms.Compose = None):
        transform = initial_transform if initial_transform is not None else transforms.ToTensor()

        dataset = ImageFolder(
            root=path,
            transform=transform,
        )

        self._data_loader = DataLoader(
            dataset=dataset,
            batch_size=self._batch_size,
            shuffle=True,
            pin_memory=True,
            num_workers=num_workers,
        )

    def _double_aug(self, images: torch.Tensor) -> torch.Tensor:
        augmented_images = torch.concat(
            [self._image_augmentation_fn(images), self._image_augmentation_fn(images)],
            dim=0,
        )
        return augmented_images

    def _log(self, epoch: int, epoch_loss: float, start_time: float):
        avg_loss = epoch_loss / len(self._data_loader)
        print(
            f"Epoch {epoch + 1}/{self._epochs} - Loss: {avg_loss:.4f} - Time Taken {((time.time() - start_time) / 60):2f}",
            flush=True
        )

    def _save_state(self, optimiser: torch.optim.Optimizer):
        torch.save(
            self._image_encoder.state_dict(),
            os.path.join(self._encoder_checkpoint_path, 'encoder.pt')
        )

        torch.save(
            optimiser.state_dict(),
            os.path.join(self._encoder_checkpoint_path, 'optimiser.pt'),
        )

    def _save_losses(self, losses: list):
        df = pd.DataFrame({"Loss": losses})
        df.to_csv(os.path.join(self._encoder_checkpoint_path, "losses.csv"), index=False)

    @abstractmethod
    def _compute_loss(self, **kwargs) -> torch.Tensor:
        raise NotImplementedError("Must be implemented by child class")

    def train(self):
        optimiser = optim.AdamW(self._image_encoder.parameters(), lr=3e-4, weight_decay=1e-4)
        scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimiser, T_max=len(self._data_loader))

        print('=== Starting Training ===', flush=True)
        scaler = GradScaler()
        epoch_losses = []
        for epoch in range(self._epochs):
            epoch_loss = 0
            start = time.time()
            for images, labels in self._data_loader:
                optimiser.zero_grad()

                images = images.to(self._device)
                augmented_images = self._double_aug(images)

                with autocast(dtype=torch.float16):
                    image_encodings = self._image_encoder(augmented_images)
                    image_encodings = nn.functional.normalize(image_encodings, p=2, dim=1)
                    encoding_similarities = image_encodings @ image_encodings.T

                loss = self._compute_loss(encoding_similarities=encoding_similarities, labels=labels)

                scaler.scale(loss).backward()
                scaler.step(optimiser)
                scaler.update()

                epoch_loss += loss.item()

            if epoch >= 15:
                scheduler.step()

            epoch_losses.append(epoch_loss)
            self._log(epoch=epoch, epoch_loss=epoch_loss, start_time=start)
            self._save_state(optimiser=optimiser)

        self._save_losses(losses=epoch_losses)

