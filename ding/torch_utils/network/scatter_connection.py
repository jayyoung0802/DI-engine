import torch
import torch.nn as nn
from typing import Tuple
from ding.hpc_rl import hpc_wrapper


def shape_fn_scatter_connection(args, kwargs) -> list:
    r"""
    Overview:
        Return shape of scatter_connection for hpc
    Returns:
        - shape (:obj:`list`): List like [B, M, N, H, W, scatter_type]
    """
    if len(args) <= 1:
        tmp = list(kwargs['x'].shape)
    else:
        tmp = list(args[1].shape)  # args[0] is __main__.ScatterConnection object
    if len(args) <= 2:
        tmp.extend(kwargs['spatial_size'])
    else:
        tmp.extend(args[2])
    tmp.append(args[0].scatter_type)
    return tmp


class ScatterConnection(nn.Module):
    r"""
    Overview:
        Scatter feature to its corresponding location
        In AlphaStar, each entity is embedded into a tensor,
        and these tensors are scattered into a feature map with map size.
    """

    def __init__(self, scatter_type: str) -> None:
        r"""
        Overview:
            Init class
        Arguments:
            - scatter_type (:obj:`str`): Supports ['add', 'cover']. If two entities have the same location, \
                scatter_type decides the first one should be covered or added to second one
        """
        super(ScatterConnection, self).__init__()
        self.scatter_type = scatter_type
        assert self.scatter_type in ['cover', 'add']

    @hpc_wrapper(
        shape_fn=shape_fn_scatter_connection,
        namedtuple_data=False,
        include_args=[0, 2],
        include_kwargs=['x', 'location'],
        is_cls_method=True
    )
    def forward(self, x: torch.Tensor, spatial_size: Tuple[int, int], location: torch.Tensor) -> torch.Tensor:
        """
        Overview:
            scatter x into a spatial feature map
        Arguments:
            - x (:obj:`tensor`): input tensor :math: `(B, M, N)` where `M` means the number of entity, `N` means \
                the dimension of entity attributes
            - spatial_size (:obj:`tuple`): Tuple[H, W], the size of spatial feature x will be scattered into
            - location (:obj:`tensor`): :math: `(B, M, 2)` torch.LongTensor, each location should be (y, x)
        Returns:
            - output (:obj:`tensor`): :math: `(B, N, H, W)` where `H` and `W` are spatial_size, return the\
                scattered feature map
        Shapes:
            - Input: :math: `(B, M, N)` where `M` means the number of entity, `N` means \
                the dimension of entity attributes
            - Size: Tuple type :math: `[H, W]`
            - Location: :math: `(B, M, 2)` torch.LongTensor, each location should be (y, x)
            - Output: :math: `(B, N, H, W)` where `H` and `W` are spatial_size

        .. note::

            When there are some overlapping in locations, ``cover`` mode will result in the loss of information, we
            use the addition as temporal substitute.
        """
        device = x.device
        B, M, N = x.shape
        H, W = spatial_size
        index = location.view(-1, 2)
        bias = torch.arange(B).mul_(H * W).unsqueeze(1).repeat(1, M).view(-1).to(device)
        index = index[:, 0] * W + index[:, 1]
        index += bias
        index = index.repeat(N, 1)
        x = x.view(-1, N).permute(1, 0)
        output = torch.zeros(N, B * H * W, device=device)
        if self.scatter_type == 'cover':
            output.scatter_(dim=1, index=index, src=x)
        elif self.scatter_type == 'add':
            output.scatter_add_(dim=1, index=index, src=x)
        output = output.reshape(N, B, H, W)
        output = output.permute(1, 0, 2, 3).contiguous()
        return output
    
    @hpc_wrapper(
        shape_fn=shape_fn_scatter_connection,
        namedtuple_data=False,
        include_args=[0, 2],
        include_kwargs=['x', 'location'],
        is_cls_method=True
    )
    def xy_forward(
            self, x: torch.Tensor, spatial_size: Tuple[int, int], coord_x: torch.Tensor, coord_y
    ) -> torch.Tensor:
        """
        Overview:
            scatter x into a spatial feature map
        Arguments:
            - x (:obj:`tensor`): input tensor :math: `(B, M, N)` where `M` means the number of entity, `N` means\
                the dimension of entity attributes
            - spatial_size (:obj:`tuple`): Tuple[H, W], the size of spatial feature x will be scattered into
            - coord_x (:obj:`tensor`): :math: `(B, M)` torch.LongTensor, each location should be x
            - coord_y (:obj:`tensor`): :math: `(B, M)` torch.LongTensor, each location should be y
        Returns:
            - output (:obj:`tensor`): :math: `(B, N, H, W)` where `H` and `W` are spatial_size, return the\
                scattered feature map
        Shapes:
            - Input: :math: `(B, M, N)` where `M` means the number of entity, `N` means\
                the dimension of entity attributes
            - Size: Tuple[H, W]
            - Coord_x: :math: `(B, M)` torch.LongTensor, each location should be x
            - Coord_y: :math: `(B, M)` torch.LongTensor, each location should be y
            - Output: :math: `(B, N, H, W)` where `H` and `W` are spatial_size

        note:
            when there are some overlapping in locations, ``cover`` mode will result in the loss of information, we
            use the addition as temporal substitute.
        """
        device = x.device
        BatchSize, Num, EmbeddingSize = x.shape
        x = x.permute(0, 2, 1)
        H, W = spatial_size
        indices = (coord_x * W + coord_y).long()
        indices = indices.unsqueeze(dim=1).repeat(1, EmbeddingSize, 1)
        output = torch.zeros(size=(BatchSize, EmbeddingSize, H, W), device=device).view(BatchSize, EmbeddingSize, H * W)
        if self.scatter_type == 'cover':
            output.scatter_(dim=2, index=indices, src=x)
        elif self.scatter_type == 'add':
            output.scatter_add_(dim=2, index=indices, src=x)
        output = output.view(BatchSize, EmbeddingSize, H, W)
        return output
