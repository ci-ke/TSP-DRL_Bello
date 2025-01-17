import torch
import numpy as np
import math
import itertools
import matplotlib.pyplot as plt
from typing import Any, Dict, List, Tuple, Union

from config import Config


def get_2city_distance(
    n1: Union[torch.Tensor, list, np.ndarray], n2: Union[torch.Tensor, list, np.ndarray]
) -> torch.Tensor:
    x1, y1, x2, y2 = n1[0], n1[1], n2[0], n2[1]
    if isinstance(n1, torch.Tensor):
        return torch.sqrt((x2 - x1).pow(2) + (y2 - y1).pow(2))
    elif isinstance(n1, (list, np.ndarray)):
        return torch.tensor(math.sqrt(pow(x2 - x1, 2) + pow(y2 - y1, 2)))
    else:
        raise TypeError


class Env_tsp:
    def __init__(self, cfg: Config) -> None:
        '''
        nodes(cities) : contains nodes and their 2 dimensional coordinates
        [city_t, 2] = [3,2] dimension array e.g. [[0.5,0.7],[0.2,0.3],[0.4,0.1]]
        '''
        self.batch = cfg.batch
        self.city_t = cfg.city_t

    def get_nodes(self, seed: int = None) -> torch.Tensor:
        '''
        return nodes:(city_t,2)
        '''
        if seed is not None:
            torch.manual_seed(seed)
        device = torch.device('cuda:0' if torch.cuda.is_available() else 'cpu')
        return torch.rand((self.city_t, 2), device=device)

    def stack_nodes(self) -> torch.Tensor:
        '''
        nodes:(city_t,2)
        return inputs:(batch,city_t,2)
        '''
        list = [self.get_nodes() for i in range(self.batch)]
        inputs = torch.stack(list, dim=0)
        return inputs

    def get_batch_nodes(self, n_samples: int, seed: int = None) -> torch.Tensor:
        '''
        return nodes:(batch,city_t,2)
        '''
        if seed is not None:
            torch.manual_seed(seed)
        device = torch.device('cuda:0' if torch.cuda.is_available() else 'cpu')
        return torch.rand((n_samples, self.city_t, 2), device=device)

    def stack_random_tours(self) -> torch.Tensor:
        '''
        tour:(city_t)
        return tours:(batch,city_t)
        '''
        list = [self.get_random_tour() for i in range(self.batch)]
        tours = torch.stack(list, dim=0)
        return tours

    def stack_l(self, inputs: torch.Tensor, tours: torch.Tensor) -> torch.Tensor:
        '''
        inputs:(batch,city_t,2)
        tours:(batch,city_t)
        return l_batch:(batch)
        '''
        list = [self.get_tour_distance(inputs[i], tours[i]) for i in range(self.batch)]
        l_batch = torch.stack(list, dim=0)
        return l_batch

    def stack_l_fast(self, inputs: torch.Tensor, tours: torch.Tensor) -> torch.Tensor:
        """
        *** this function is faster version of stack_l! ***
        inputs: (batch, city_t, 2), Coordinates of nodes
        tours: (batch, city_t), predicted tour
        d: (batch, city_t, 2)
        """
        d = torch.gather(input=inputs, dim=1, index=tours[:, :, None].repeat(1, 1, 2))
        # index: (batch, city_t, 2)
        return torch.sum((d[:, 1:] - d[:, :-1]).norm(p=2, dim=2), dim=1) + (
            d[:, 0] - d[:, -1]
        ).norm(
            p=2, dim=1
        )  # distance from last node to first selected node)

    def show(self, nodes: torch.Tensor, tour: torch.Tensor) -> None:
        nodes = nodes.cpu().detach()
        print('distance:{:.3f}'.format(self.get_tour_distance(nodes, tour)))
        print(tour)
        plt.figure()
        plt.plot(nodes[:, 0], nodes[:, 1], 'yo', markersize=16)
        np_tour = tour.cpu().detach()
        np_fin_tour = [tour[-1].item(), tour[0].item()]
        plt.plot(nodes[np_tour, 0], nodes[np_tour, 1], 'k-', linewidth=0.7)
        plt.plot(nodes[np_fin_tour, 0], nodes[np_fin_tour, 1], 'k-', linewidth=0.7)
        for i in range(self.city_t):
            plt.text(nodes[i, 0], nodes[i, 1], str(i), size=10, color='b')
        plt.show()

    def shuffle(self, inputs: torch.Tensor) -> torch.Tensor:
        '''
        shuffle nodes order with a set of xy coordinate
        inputs:(batch,city_t,2)
        return shuffle_inputs:(batch,city_t,2)
        '''
        shuffle_inputs = torch.zeros(inputs.size())
        for i in range(self.batch):
            perm = torch.randperm(self.city_t)
            shuffle_inputs[i, :, :] = inputs[i, perm, :]
        return shuffle_inputs

    def back_tours(
        self,
        pred_shuffle_tours: torch.Tensor,
        shuffle_inputs: torch.Tensor,
        test_inputs: torch.Tensor,
        device: torch.device,
    ) -> torch.Tensor:
        '''
        pred_shuffle_tours:(batch,city_t): elements correspond to permutation of shuffle_inputs
        shuffle_inputs:(batch,city_t,2)
        test_inputs:(batch,city_t,2): original permutation
        return pred_tours:(batch,city_t)
        '''
        pred_tours = []
        for i in range(self.batch):
            pred_tour = []
            for j in range(self.city_t):
                xy_temp = shuffle_inputs[i, pred_shuffle_tours[i, j]].to(device)
                for k in range(self.city_t):
                    if torch.all(torch.eq(xy_temp, test_inputs[i, k])):
                        pred_tour.append(torch.tensor(k))
                        if len(pred_tour) == self.city_t:
                            pred_tours.append(torch.stack(pred_tour, dim=0))
                        break
        pred_tours_tensor = torch.stack(pred_tours, dim=0)
        return pred_tours_tensor

    def get_tour_distance(
        self, nodes: torch.Tensor, tour: torch.Tensor
    ) -> torch.Tensor:
        '''
        nodes:(city_t,2), tour:(city_t)
        l(= total distance) = l(0-1) + l(1-2) + l(2-3) + ... + l(18-19) + l(19-0) @20%20->0
        return l:(1)
        '''
        l = torch.tensor(0.0)
        for i in range(self.city_t):
            l += get_2city_distance(nodes[tour[i]], nodes[tour[(i + 1) % self.city_t]])
        return l

    def get_random_tour(self) -> torch.Tensor:
        '''
        return tour:(city_t)
        '''
        tour: List[int] = []
        while set(tour) != set(range(self.city_t)):
            city = np.random.randint(self.city_t)
            if city not in tour:
                tour.append(city)
        tour_tensor = torch.from_numpy(np.array(tour)).long()
        return tour_tensor

    def get_optimal_tour(self, nodes: torch.Tensor) -> torch.Tensor:
        # dynamic programming algorithm to solve TSP
        # https://blog.csdn.net/qq_39559641/article/details/101209534
        points = nodes.cpu().numpy()
        all_distances = np.array(
            [[get_2city_distance(x, y) for y in points] for x in points]
        )
        # initial value - just distance from every other point to node 0 + keep the track of tour
        A: Dict[Tuple[int, frozenset], Tuple[np.float32, List[int]]] = {
            (idx, frozenset()): (dist, [idx])
            for idx, dist in enumerate(all_distances[1:, 0], start=1)
        }
        # key(state): (start node, {nodes need to visit before return to node 0})
        # value: (distance, [visit sequence])
        cnt = all_distances.shape[0]
        for m in range(2, cnt):
            B = {}
            for S in (frozenset(C) for C in itertools.combinations(range(1, cnt), m)):
                for j in S:
                    R = S - {j}
                    B[(j, R)] = min(
                        (
                            all_distances[j, k] + A[(k, R - {k})][0],
                            [j] + A[(k, R - {k})][1],
                        )
                        for k in R
                    )  # this will use 0th index of tuple for ordering, the same as if key=itemgetter(0) used
            A = B
        res = min(
            (all_distances[0, node] + dist, [0] + seq)
            for (node, _), (dist, seq) in A.items()
        )
        tour = torch.tensor(res[1]).long()
        return tour


if __name__ == '__main__':
    from types import SimpleNamespace

    test_input = torch.tensor([(0, 0), (1, 0), (4, 0), (0, -3)])
    cfg: Any = SimpleNamespace(batch=1, city_t=4)
    env = Env_tsp(cfg)
    optimal_tour = env.get_optimal_tour(test_input)
    env.show(test_input, optimal_tour)
