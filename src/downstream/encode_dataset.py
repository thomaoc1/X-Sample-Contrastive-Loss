import argparse
import os

import torch
import torchvision.transforms as transforms
import torchvision.datasets as datasets
from torch.utils.data import DataLoader
from torchvision.datasets import ImageFolder
from tqdm import tqdm

from src.pretraining.encoder import ResNetEncoder


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument('encoder_weights_path', type=str, help='Path to weights for encoder')
    parser.add_argument('model', choices=['xclr', 'simclr'], type=str, help='Model used for encoder training')
    parser.add_argument('model_id', type=str, help='Unique identifier for trained model (ex. b256_AdamW_3e-4)')
    parser.add_argument(
        '--task',
        '-t',
        default=None,
        type=str,
        required=True,
        help="Path to the dataset to be encoded or choices=['imgnet-s', 'cifar10', 'stl10', 'bgd-ms', 'bgd-mr', 'bgd-nb']"
    )
    parser.add_argument(
        '--name'
    )
    return parser.parse_args()


class DatasetEncoder:
    def __init__(self, path: str, task: str, model: str, model_id: str, name: str | None):
        self._model = model
        self._model_id = model_id
        self._name = name
        self._task = task
        self._device = 'cuda' if torch.cuda.is_available() else 'cpu'
        self._base_save_path = os.path.join(
            'datasets/encoded/',
            self._model,
            self._model_id,
            self._name if self._name else self._task
        )

        if not os.path.exists(self._base_save_path):
            os.makedirs(self._base_save_path)

        self._init_encoder(path)
        if self._task == 'cifar10':
            train_loader, test_loader = DatasetEncoder.init_cifar_loaders()
        elif self._task == 'stl10':
            train_loader, test_loader = DatasetEncoder.init_stl10_loaders()
        elif self._task == 'imgnet-s':
            train_loader, test_loader = DatasetEncoder.init_imgnet_s_loaders()
        elif self._task.find('bgd-') > -1:
            sub_task = self._task.split('-')[1]
            task_to_dir = {
                'ms': 'mixed_same',
                'mr': 'mixed_rand',
                'nb': 'only_fg',
            }
            if not task_to_dir.get(sub_task, None):
                raise ValueError(f'Task {sub_task} does not exist')
            test_loader = DatasetEncoder.init_imgnet9_loaders(task_to_dir[sub_task])
            train_loader = None
        else:
            assert os.path.exists(self._task), "Path does not exist"
            train_loader = self.init_img_folder_loader()
            test_loader = None

        self._encode(train_loader, test_loader)

    def _init_encoder(self, path: str):
        image_encoder = ResNetEncoder(detach_head=True).to(self._device)
        image_encoder.load_state_dict(
            torch.load(
                path,
                weights_only=True,
                map_location=self._device
            )
        )

        image_encoder.eval()
        image_encoder.requires_grad_(False)
        self._image_encoder = image_encoder

    def _encode(self, test_loader: DataLoader | None, train_loader: DataLoader | None):
        if train_loader:
            train_encodings, train_labels = self._extract_features_dataset(dataloader=train_loader)
            self._save_encoding_label_pairs(train_encodings, train_labels, 'train.pt')

        if test_loader:
            test_encodings, test_labels = self._extract_features_dataset(dataloader=test_loader)
            self._save_encoding_label_pairs(test_encodings, test_labels, 'test.pt')

    def _extract_features_dataset(self, dataloader: DataLoader):
        encodings_list, labels_list = [], []
        for img, label in tqdm(dataloader, total=len(dataloader), desc="Extracting Features"):
            with torch.no_grad():
                encodings = self._image_encoder(img.to(self._device)).flatten(1)
            encodings_list.append(encodings.cpu())
            labels_list.append(label.cpu())
        encodings = torch.cat(encodings_list, dim=0)
        labels = torch.cat(labels_list, dim=0)
        return encodings, labels

    def _save_encoding_label_pairs(self, encodings, labels, filename):
        final_path = os.path.join(self._base_save_path, filename)
        torch.save(
            {
                'encodings': encodings,
                'labels': labels,
            },
            final_path,
        )
        print(f'Encodings saved in {final_path}.')

    @staticmethod
    def init_cifar_loaders():
        transform = transforms.Compose(
            [
                transforms.Resize(32),
                transforms.ToTensor(),
            ]
        )

        train_dataset = datasets.CIFAR10(root="./data", train=True, transform=transform, download=True)
        test_dataset = datasets.CIFAR10(root="./data", train=False, transform=transform, download=True)

        train_loader = DataLoader(train_dataset, batch_size=128, shuffle=True)
        test_loader = DataLoader(test_dataset, batch_size=128, shuffle=False)

        return train_loader, test_loader

    @staticmethod
    def init_stl10_loaders():
        transform = transforms.Compose(
            [
                transforms.Resize(96),
                transforms.ToTensor(),
            ]
        )

        train_dataset = datasets.STL10(root="./data", split="train", transform=transform, download=True)
        test_dataset = datasets.STL10(root="./data", split="test", transform=transform, download=True)

        train_loader = DataLoader(train_dataset, batch_size=128, shuffle=True)
        test_loader = DataLoader(test_dataset, batch_size=128, shuffle=False)

        return train_loader, test_loader

    @staticmethod
    def init_imgnet9_loaders(task: str):
        transform = transforms.Compose(
            [
                transforms.Resize((224, 224)),
                transforms.ToTensor(),
            ]
        )

        base_path = 'datasets/ImageNet9/'
        test_path = os.path.join(base_path, task, 'val')

        test_set = ImageFolder(
            root=test_path,
            transform=transform,
        )

        test_loader = DataLoader(test_set, batch_size=128)

        return test_loader

    @staticmethod
    def init_imgnet_s_loaders():
        transform = transforms.Compose(
            [
                transforms.Resize((224, 224)),
                transforms.ToTensor(),
            ]
        )

        base_path = os.path.join('datasets', 'ImageNet-S-50')
        train_path = os.path.join(base_path, 'train')
        test_path = os.path.join(base_path, 'test')

        train_set = ImageFolder(
            root=train_path,
            transform=transform
        )

        test_set = ImageFolder(
            root=test_path,
            transform=transform,
        )

        train_loader = DataLoader(train_set, batch_size=128)
        test_loader = DataLoader(test_set, batch_size=128)

        return train_loader, test_loader

    def init_img_folder_loader(self):
        transform = transforms.Compose(
            [
                transforms.Resize((224, 224)),
                transforms.ToTensor(),
            ]
        )

        dataset = ImageFolder(
            root=self._task,
            transform=transform,
        )

        train_loader = DataLoader(dataset, batch_size=128)

        return train_loader


if __name__ == '__main__':
    args = parse_args()
    de = DatasetEncoder(
        path=args.encoder_weights_path,
        task=args.task,
        model=args.model,
        model_id=args.model_id,
        name=args.name,
    )
