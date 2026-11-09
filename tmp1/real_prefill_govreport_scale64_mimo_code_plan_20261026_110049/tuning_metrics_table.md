# Tuning Metrics

Objective-change columns use (after - before) / before for objective = latency * energy * mc. Negative values mean the objective decreased and improved; positive values mean it increased and regressed.

| Run | Latency | Energy | MC | Objective | Obj vs Initial | Obj vs Previous Best | New Best | Applied Change |
|---|---:|---:|---:|---:|---:|---:|:---:|---|
| init | 7.129e+10 | 1.288e+14 | 228.7 | 2.099e+27 | +0.00% | N/A | yes | initial hardware |
| iter001 | 4.669e+10 | 8.696e+13 | 237.6 | 9.647e+26 | -54.05% | -54.05% | yes | increase_compute_units_to_16384: chiplets.compute_units: {'4096': 16}->{'16384': 16}; chiplets.macs: {'[8,8,8,8]': 16}->{'[8,8,16,16]': 16}; compute_units: changed on 16 chiplets |
| iter002 | 4.571e+10 | 8.721e+13 | 418.3 | 1.668e+27 | -20.57% | +72.86% | no | increase_nop_bw_to_256: nop_bw: 128->256 |
| iter003 | 2.377e+10 | 7.969e+13 | 448.2 | 8.491e+26 | -59.56% | -11.98% | yes | increase_num_chiplets_to_32_with_tp_32: num_chiplets: 16->32; chip_y: 4->8 (derived); tensor_parall: 16->32; +6 more |
| iter004 | 2.359e+10 | 7.96e+13 | 477 | 8.956e+26 | -57.34% | +5.48% | no | increase_dram_bw_to_128: dram_bw: 64->128 |
| iter005 | 2.098e+10 | 5.323e+13 | 820.6 | 9.163e+26 | -56.35% | +7.92% | no | increase_buffer_size_to_32768: chiplets.buffer_size: {'8192': 32}->{'32768': 32}; buffer_size: changed on 32 chiplets |
