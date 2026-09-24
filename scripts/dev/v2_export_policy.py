"""Inference-only export adapter for the native ScalablePolicy and its versioned financial inputs.

The C++ model and live distribution remain authoritative. This module exists
only to convert their saved parameters to ONNX, with independent native checks.
It is not a training implementation.
"""
import math
from pathlib import Path

import numpy as np
import torch
from torch import nn
from v2_onnx_package import financial_features_mode


INPUT_NAMES = ('structured', 'global_spatial', 'regional_spatial', 'local_spatial',
    'companies', 'company_mask', 'towns', 'town_mask', 'industries', 'industry_mask',
    'stations', 'station_mask', 'vehicles', 'vehicle_mask', 'graph_nodes', 'graph_node_mask',
    'graph_edge_index', 'graph_edges', 'graph_edge_mask', 'candidate_features', 'candidate_family',
    'candidate_mask', 'family_mask', 'hidden_state', 'recurrent_reset')
OUTPUT_NAMES = ('family_logits', 'candidate_logits', 'value', 'next_hidden', 'probabilities')
TABLES = (('company', 15, 32), ('town', 128, 24), ('industry', 256, 24),
          ('station', 512, 32), ('vehicle', 1024, 40))


def signed_log(values, native_divisor):
    return torch.sign(values) * torch.log1p(values.abs() * native_divisor) / math.log1p(1e9)


class ExportPolicy(nn.Module):
    def __init__(self, financial_features="raw"):
        super().__init__()
        self.financial_features = financial_features_mode(financial_features)
        self.structured_1 = nn.Linear(512, 256)
        self.structured_2 = nn.Linear(256, 128)
        self.spatial_1 = nn.Conv2d(32, 32, 5, stride=2, padding=2)
        self.spatial_2 = nn.Conv2d(32, 64, 3, stride=2, padding=1)
        self.spatial_3 = nn.Conv2d(64, 128, 3, stride=2, padding=1)
        self.spatial_projection = nn.Linear(384, 256)
        for name, _, features in TABLES:
            setattr(self, name + '_projection', nn.Linear(features, 128))
        self.entity_query = nn.Linear(128, 128)
        self.entity_key = nn.Linear(128, 128)
        self.entity_value = nn.Linear(128, 128)
        self.entity_fusion = nn.Linear(640, 128)
        self.entity_norm = nn.LayerNorm(128)
        self.entity_feedforward = nn.Linear(128, 128)
        self.entity_output_norm = nn.LayerNorm(128)
        self.entity_type_embedding = nn.Parameter(torch.empty(5, 128))
        self.graph_node_projection = nn.Linear(24, 128)
        self.graph_edge_projection = nn.Linear(16, 128)
        self.graph_message = nn.Linear(256, 128)
        self.graph_norm = nn.LayerNorm(128)
        self.graph_query = nn.Linear(128, 128)
        self.fusion = nn.Linear(768, 256)
        self.fusion_norm = nn.LayerNorm(256)
        self.memory = nn.GRUCell(256, 256)
        self.family_head = nn.Linear(256, 12)
        self.candidate_family_embedding = nn.Embedding(12, 128)
        self.candidate_projection = nn.Linear(32, 128)
        self.candidate_query = nn.Linear(256, 128)
        self.candidate_bias = nn.Linear(128, 1)
        self.value_head = nn.Linear(256, 1)

    def spatial(self, tensor):
        tensor = torch.nn.functional.silu(self.spatial_1(tensor))
        tensor = torch.nn.functional.silu(self.spatial_2(tensor))
        return torch.nn.functional.silu(self.spatial_3(tensor)).mean((2, 3))

    def pool(self, tokens, mask, query):
        scores = (self.entity_key(tokens) * query.unsqueeze(1)).sum(-1) / math.sqrt(128)
        scores = scores.masked_fill(~mask, -1e9)
        weights = torch.exp(scores - scores.max(1, keepdim=True).values) * mask.to(torch.float32)
        weights = weights / weights.sum(1, keepdim=True).clamp_min(1e-12)
        return torch.bmm(weights.unsqueeze(1), self.entity_value(tokens)).squeeze(1)

    def forward(self, structured, global_spatial, regional_spatial, local_spatial,
                companies, company_mask, towns, town_mask, industries, industry_mask,
                stations, station_mask, vehicles, vehicle_mask, graph_nodes, graph_node_mask,
                graph_edge_index, graph_edges, graph_edge_mask, candidate_features, candidate_family,
                candidate_mask, family_mask, hidden_state, recurrent_reset):
        if self.financial_features == 'signed-log-v1':
            # The graph accepts original public tensors. Apply exactly the
            # native signed-log fields once, before any policy encoder.
            structured = torch.cat((structured[:, :8], signed_log(structured[:, 8:10], 1e9), structured[:, 10:]), 1)
            companies = torch.cat((companies[:, :, :2], signed_log(companies[:, :, 2:5], 1e9), companies[:, :, 5:]), 2)
            candidate_features = torch.cat((candidate_features[:, :, :13], signed_log(candidate_features[:, :, 13:14], 1e6), candidate_features[:, :, 14:]), 2)
        structured_hidden = torch.tanh(self.structured_2(torch.tanh(self.structured_1(structured))))
        spatial_hidden = torch.tanh(self.spatial_projection(torch.cat([
            self.spatial(global_spatial), self.spatial(regional_spatial), self.spatial(local_spatial)], 1)))
        query = self.entity_query(structured_hidden)
        tables = [(companies, company_mask), (towns, town_mask), (industries, industry_mask),
                  (stations, station_mask), (vehicles, vehicle_mask)]
        summaries = []
        for i, ((name, _, _), (features, mask)) in enumerate(zip(TABLES, tables, strict=True)):
            tokens = torch.tanh(getattr(self, name + '_projection')(features)) + self.entity_type_embedding[i]
            summaries.append(self.pool(tokens, mask, query))
        entity_hidden = torch.tanh(self.entity_fusion(torch.cat(summaries, 1)))
        entity_hidden = self.entity_norm(entity_hidden + query)
        entity_hidden = self.entity_output_norm(entity_hidden + torch.nn.functional.silu(self.entity_feedforward(entity_hidden)))

        nodes = torch.tanh(self.graph_node_projection(graph_nodes))
        edges = torch.tanh(self.graph_edge_projection(graph_edges))
        sources = torch.where(graph_edge_mask, graph_edge_index[:, :, 0], torch.zeros_like(graph_edge_index[:, :, 0]))
        destinations = torch.where(graph_edge_mask, graph_edge_index[:, :, 1], torch.zeros_like(graph_edge_index[:, :, 1]))
        source_nodes = nodes.gather(1, sources.unsqueeze(-1).expand(-1, -1, 128))
        messages = torch.tanh(self.graph_message(torch.cat([source_nodes, edges], -1)))
        messages = messages * graph_edge_mask.unsqueeze(-1).to(torch.float32)
        aggregate = torch.zeros_like(nodes).scatter_add(1, destinations.unsqueeze(-1).expand(-1, -1, 128), messages)
        degree = torch.zeros_like(nodes[:, :, :1]).scatter_add(1, destinations.unsqueeze(-1), graph_edge_mask.unsqueeze(-1).to(torch.float32))
        nodes = self.graph_norm(nodes + aggregate / degree.clamp_min(1))
        nodes = nodes * graph_node_mask.unsqueeze(-1).to(torch.float32)
        graph_hidden = self.pool(nodes, graph_node_mask, self.graph_query(structured_hidden))

        tokens = torch.tanh(self.candidate_projection(candidate_features))
        families = torch.where(candidate_mask, candidate_family, torch.zeros_like(candidate_family))
        tokens = tokens + self.candidate_family_embedding(families)
        weights = candidate_mask.to(torch.float32)
        candidate_summary = (tokens * weights.unsqueeze(-1)).sum(1) / weights.sum(1, keepdim=True).clamp_min(1)
        fused = torch.nn.functional.silu(self.fusion_norm(self.fusion(torch.cat([
            structured_hidden, spatial_hidden, entity_hidden, graph_hidden, candidate_summary], 1))))
        reset_hidden = hidden_state * (~recurrent_reset).to(torch.float32).unsqueeze(1)
        next_hidden = self.memory(fused, reset_hidden)
        family_logits = self.family_head(next_hidden).masked_fill(~family_mask, -1e9)
        candidate_logits = (tokens * self.candidate_query(next_hidden).unsqueeze(1)).sum(-1) / math.sqrt(128)
        candidate_logits = (candidate_logits + self.candidate_bias(tokens).squeeze(-1)).masked_fill(~candidate_mask, -1e9)
        value = self.value_head(next_hidden).squeeze(-1)

        family_logp = torch.log_softmax(family_logits.masked_fill(~family_mask, -torch.inf), 1)
        membership = (candidate_family.unsqueeze(1) == torch.arange(12, device=candidate_family.device).view(1, 12, 1)) & candidate_mask.unsqueeze(1)
        grouped = candidate_logits.unsqueeze(1).expand(-1, 12, -1).masked_fill(~membership, -torch.inf)
        grouped = torch.where(family_mask.unsqueeze(2), grouped, torch.zeros_like(grouped))
        partition = torch.logsumexp(grouped, 2)
        partition = torch.where(family_mask, partition, torch.zeros_like(partition))
        logits = candidate_logits - partition.gather(1, candidate_family) + family_logp.gather(1, candidate_family)
        logits = torch.where(candidate_mask, logits, torch.zeros_like(logits)).masked_fill(~candidate_mask, -torch.inf)
        logp = torch.log_softmax(logits, 1)
        probabilities = torch.where(candidate_mask, torch.exp(logp), torch.zeros_like(logp))
        return family_logits, candidate_logits, value, next_hidden, probabilities


def load_export_policy(weights, financial_features='raw'):
    mode = financial_features_mode(financial_features)
    state = torch.jit.load(str(weights), map_location='cpu').state_dict()
    key, prefix = 'development_financial_features', 'development_preprocessed_policy.'
    if mode == 'raw':
        if key in state or any(k.startswith(prefix) for k in state):
            raise ValueError('Raw-input export refuses tagged/preprocessed weights')
    else:
        tag = state.pop(key, None)
        if tag is None or tag.dtype != torch.uint8 or tag.dim() != 1 or not 1 <= tag.numel() <= 64:
            raise ValueError('Financial feature metadata shape/type differs')
        try:
            actual = bytes(tag.cpu().tolist()).decode('ascii')
        except UnicodeDecodeError as exc:
            raise ValueError('Financial feature metadata encoding differs') from exc
        if actual != mode or not state or any(not k.startswith(prefix) for k in state):
            raise ValueError('Export weights require different financial preprocessing or archive layout')
        state = {k[len(prefix):]: value for k, value in state.items()}
    if not all(t.dtype == torch.float32 and torch.isfinite(t).all() for t in state.values()):
        raise ValueError('Export weights must be finite float32 parameters')
    model = ExportPolicy(mode).eval()
    model.load_state_dict(state, strict=True)
    return model


def load_raw_policy(weights):
    return load_export_policy(weights, 'raw')


def read_native_inputs(observation, candidates, *, hidden=None, reset=False):
    """Decode only the existing public binary tensors; reject incompatible data."""
    if any(not Path(p).is_absolute() or not Path(p).is_file() for p in (observation, candidates)):
        raise ValueError('Native V2 tensors must be existing absolute files')
    raw = Path(observation).read_bytes()
    actions = Path(candidates).read_bytes()
    if len(raw) != 2182927 or len(actions) != 790528:
        raise ValueError('Native V2 tensor byte lengths differ')
    position = 0
    def read(shape, dtype='<f4'):
        nonlocal position
        count = math.prod(shape)
        tensor = np.frombuffer(raw, dtype=dtype, count=count, offset=position).copy().reshape(shape)
        position += count * np.dtype(dtype).itemsize
        if dtype == 'u1':
            if np.any(tensor > 1):
                raise ValueError('Native entity/graph mask must be binary')
            tensor = tensor.astype(np.bool_)
        elif not np.isfinite(tensor).all():
            raise ValueError('Native public features must be finite')
        return torch.from_numpy(tensor)
    inputs = [read((1, 512)), read((1, 32, 64, 64)), read((1, 32, 64, 64)), read((1, 32, 32, 32))]
    if inputs[0][:, 13:16].abs().sum() != 0:
        raise ValueError('Native seed features must remain redacted')
    for _, capacity, width in TABLES:
        inputs.extend([read((1, capacity, width)), read((1, capacity), 'u1')])
    if inputs[12][:, :, 7:9].abs().sum() != 0:
        raise ValueError('Native private breakdown features must remain redacted')
    previous = (-1., -1.)
    for row in inputs[12][0, inputs[13][0]]:
        identity = (0. if row[2].item() == 1. else 1., row[0].item())
        if identity <= previous:
            raise ValueError('Native vehicle rows must follow public identity order')
        previous = identity
    nodes, node_mask = read((1, 2048, 24)), read((1, 2048), 'u1')
    edges, edge_mask = read((1, 8192, 16)), read((1, 8192), 'u1')
    edge_index = torch.round(edges[:, :, :2] * 2047).to(torch.int64)
    if position != len(raw) or ((edge_index < 0) | (edge_index >= 2048))[edge_mask].any():
        raise ValueError('Native graph layout or active indices differ')
    inputs.extend([nodes, node_mask, edge_index, edges, edge_mask])
    features = torch.from_numpy(np.frombuffer(actions, dtype='<f4', count=4096*32).copy().reshape(1, 4096, 32))
    parameters = np.frombuffer(actions, dtype='<u4', count=4096*16, offset=4096*32*4).copy().reshape(4096, 16)
    raw_mask = np.frombuffer(actions, dtype='u1', count=4096, offset=4096*(32+16)*4).copy()
    if not np.isin(raw_mask, [0, 1]).all() or not raw_mask.any() or not torch.isfinite(features).all():
        raise ValueError('Native candidate mask/features differ')
    mask = torch.from_numpy(raw_mask.astype(np.bool_)).unsqueeze(0)
    family = torch.from_numpy(parameters[:, 0].astype(np.int64)).unsqueeze(0)
    if ((family < 0) | (family >= 12))[mask].any():
        raise ValueError('Active candidate family outside the native inventory')
    family = torch.where(mask, family, torch.zeros_like(family))
    family_mask = torch.zeros((1, 12), dtype=torch.bool)
    family_mask[0, family[mask]] = True
    hidden = torch.zeros((1, 256)) if hidden is None else hidden
    if hidden.shape != (1, 256) or hidden.dtype != torch.float32 or hidden.device.type != 'cpu' or not torch.isfinite(hidden).all() or type(reset) is not bool:
        raise ValueError('Export hidden state or reset flag differs')
    return tuple(inputs + [features, family, mask, family_mask, hidden, torch.tensor([reset], dtype=torch.bool)])
