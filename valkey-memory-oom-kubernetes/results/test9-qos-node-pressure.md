# Test 9: QoS class vs. node memory pressure (Burstable vs. Guaranteed)

## Setup
Both runs pinned a Valkey pod and a "neighbor" memory-hog pod (plain Python process that
allocates and touches a `bytearray`, forcing real RSS) onto the same single node
(`lke682950-1007885-2x68h`, ~6GB kubelet-allocatable / ~7.76GB physical) via
`schedulingPolicy.affinity.nodeAffinity` / `nodeSelector`, then pushed real memory usage up until
the node ran low and something had to give.

## Run 1: Burstable Valkey (64Mi request / 4Gi limit) vs. Guaranteed neighbor (4.6Gi request=limit)
- Neighbor allocated and touched ~4.5GB (`request==limit`, Guaranteed QoS).
- Valkey (Burstable) was loaded with real `valkey-benchmark` traffic to only ~977MB `used_memory`
  — far less than the neighbor's 4.5GB.
- Result: **`kubelet`'s node-pressure eviction manager evicted the Valkey pod twice in a row**,
  with this exact message both times:
  > `The node was low on resource: memory. Threshold quantity: 100Mi, available: 93696Ki.
  > Container server was using 977060Ki, request is 64Mi, has larger consumption of memory.`
- The neighbor pod (using 4.6x more absolute memory) was never touched. `kubectl get events` shows
  `Evicted` (soft, kubelet-level eviction), not `OOMKilled` (hard, kernel-level) for this run.
- Mechanism: kubelet's eviction manager ranks Burstable/BestEffort pods for eviction by how far
  their usage exceeds their **request**, not by absolute usage. A pod with a 64Mi request using
  977Mi looks far worse by that metric than one requesting and using 4.6Gi.

## Run 2 (reversed): Guaranteed Valkey (1.5Gi request=limit) vs. Burstable neighbor (64Mi
request / 6Gi limit)
- Neighbor allocated ~4.5GB again (now Burstable: tiny request, big limit).
- Valkey (Guaranteed) was loaded to ~894MB `used_memory`, still well under its own 1.5Gi limit.
- Result: **the neighbor pod was `OOMKilled`** (`exitCode: 137`, `reason: OOMKilled`,
  confirmed via `containerStatuses[0].state`) while the **Guaranteed Valkey pod kept running
  untouched** (`DBSIZE` unchanged, no restart). This time it was a real kernel-level OOM kill
  (no kubelet `Evicted` event, no node `MemoryPressure` condition observed — the kernel got there
  first), consistent with the kernel OOM-killer scoring by `oom_score_adj`, which is very negative
  (protected) for Guaranteed pods and scales toward "evict me first" for Burstable pods with a
  tiny request relative to their limit.

## Takeaway for the post
Two independent, opposite-direction, fully reproduced results on the same node:
- A Burstable Valkey pod can be evicted by `kubelet` ahead of a neighbor using several times more
  absolute memory, purely because of how far its usage sits above its own request.
- The same Valkey pod, made Guaranteed (request == limit), survives real node memory pressure that
  kills a Burstable neighbor using comparable amounts of memory instead.
- The practical rule: for anything you don't want casually evicted under node pressure, set
  `requests == limits` (Guaranteed QoS). A generous `limit` with a token `request` looks fine until
  the node gets tight, and then it's often the first thing killed — regardless of how much memory
  it's actually using compared to its neighbors.
