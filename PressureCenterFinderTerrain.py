import numpy as np
from collections import deque

def haversine_km(lat1, lon1, lat2, lon2):
    R = 6371.0
    dlat = np.radians(lat2 - lat1)
    dlon = np.radians(lon2 - lon1)
    a = np.sin(dlat/2.0)**2 + np.cos(np.radians(lat1))*np.cos(np.radians(lat2))*np.sin(dlon/2.0)**2
    return 2.0 * R * np.arcsin(np.sqrt(a))

def gaussian_kernel1d(sigma, radius=None, dtype=np.float32):
    if sigma <= 0:
        return np.array([1.0], dtype=dtype)
    if radius is None:
        radius = int(np.ceil(3.0 * sigma))
    x = np.arange(-radius, radius+1, dtype=dtype)
    k = np.exp(-(x*x) / (2.0 * dtype(sigma)**2), dtype=dtype)
    k /= k.sum(dtype=dtype)
    return k.astype(dtype, copy=False)

def conv1d_axis(a, k, axis):
    pad = len(k)//2
    pads = [(0,0)] * a.ndim
    pads[axis] = (pad, pad)
    a_pad = np.pad(a, pads, mode="edge")
    shape = list(a_pad.shape)
    shape[axis] = a.shape[axis]
    shape.insert(axis+1, len(k))
    strides = list(a_pad.strides)
    strides.insert(axis+1, a_pad.strides[axis])
    from numpy.lib.stride_tricks import as_strided
    win = as_strided(a_pad, shape=shape, strides=strides)
    # tensordot allocates only the output (same shape as a)
    return np.tensordot(win, k, axes=([axis+1],[0]))

def gaussian_blur2d(a, sigma_y, sigma_x, dtype=np.float32):
    ky = gaussian_kernel1d(sigma_y, dtype=dtype)
    kx = gaussian_kernel1d(sigma_x, dtype=dtype)
    out = a
    if len(ky) > 1:
        out = conv1d_axis(out, ky, axis=0).astype(dtype, copy=False)
    if len(kx) > 1:
        out = conv1d_axis(out, kx, axis=1).astype(dtype, copy=False)
    return out

def _box_blur1d(a, radius_cells, axis):
    r = int(max(0, radius_cells))
    if r <= 0:
        return a
    k = 2*r + 1
    kern = np.ones(k, dtype=a.dtype) / k
    return conv1d_axis(a, kern, axis=axis).astype(a.dtype, copy=False)

def box_blur2d_mean_aniso(a, radius_y_cells, radius_x_cells):
    # in-place style: reuse names so intermediates can be freed
    out = _box_blur1d(a, radius_y_cells, axis=0)
    out = _box_blur1d(out, radius_x_cells, axis=1)
    return out

def local_std_box_aniso(a, radius_y_cells=3, radius_x_cells=3):
    # compute std via means; uses ~3 arrays of size a for peak
    m  = box_blur2d_mean_aniso(a,  radius_y_cells, radius_x_cells)
    m2 = box_blur2d_mean_aniso(a*a, radius_y_cells, radius_x_cells)
    var = np.clip(m2 - m*m, 0.0, None, out=m2)  # reuse m2 buffer for var
    std = np.sqrt(var, out=var)                 # std in-place on var buffer
    return std  # (m is freed when we return; caller can delete std when done)

def local_extrema_3x3(a, wrap_lon=True):
    ny, nx = a.shape
    roll = lambda dy,dx: np.roll(np.roll(a, dy, 0), dx, 1)
    nbrs = [roll(-1,0), roll(1,0), roll(0,-1), roll(0,1),
            roll(-1,-1), roll(-1,1), roll(1,-1), roll(1,1)]
    if not wrap_lon:
        edge = np.zeros_like(a, dtype=bool)
        edge[[0,-1],:] = True
        edge[:,[0,-1]] = True
    lo = np.ones(a.shape, dtype=bool)
    hi = np.ones(a.shape, dtype=bool)
    for n in nbrs:
        lo &= (a < n)
        hi &= (a > n)
    if not wrap_lon:
        lo &= ~edge
        hi &= ~edge
    return lo, hi

def ring_prominence(mslp, lats, lons, iy, ix, r_inner_km=200, r_outer_km=600, for_low=True):
    lat0 = lats[iy, ix]; lon0 = lons[iy, ix]
    lat_min = lat0 - r_outer_km/111.0
    lat_max = lat0 + r_outer_km/111.0
    lon_pad = r_outer_km / (111.0*np.cos(np.radians(lat0)) + 1e-6)
    lon_min = lon0 - lon_pad; lon_max = lon0 + lon_pad
    box = (lats >= lat_min) & (lats <= lat_max) & (lons >= lon_min) & (lons <= lon_max)
    if not np.any(box): return 0.0
    d = haversine_km(lat0, lon0, lats[box], lons[box])
    ring = (d >= r_inner_km) & (d <= r_outer_km)
    if not np.any(ring): return 0.0
    ring_mean = mslp[box][ring].mean(dtype=mslp.dtype)
    center = mslp[iy, ix]
    return float((ring_mean - center) if for_low else (center - ring_mean))

def nonmax_separation(cands, lats, lons, min_sep_km=400):
    if not cands: return []
    keep, used = [], np.zeros(len(cands), dtype=bool)
    order = np.argsort([-c["prom"] for c in cands])
    for idx in order:
        if used[idx]: continue
        ci = cands[idx]; keep.append(ci)
        for j in order:
            if used[j]: continue
            cj = cands[j]
            dist = haversine_km(lats[ci["iy"],ci["ix"]], lons[ci["iy"],ci["ix"]],
                                lats[cj["iy"],cj["ix"]], lons[cj["iy"],cj["ix"]])
            if dist < min_sep_km:
                used[j] = True
    return keep

# def snap_to_extremum_window(mslp, iy, ix,
#                             for_low=True,
#                             radius=3,        # 2 => 5x5, 3 => 7x7
#                             wrap_lon=True,   # wrap in x (longitude)
#                             wrap_lat=False,  # usually False
#                             eps=0.0):
#     ny, nx = mslp.shape
#     i0, j0 = int(iy), int(ix)

#     # Build square window index grids
#     di = np.arange(-radius, radius+1, dtype=int)
#     dj = np.arange(-radius, radius+1, dtype=int)
#     DI, DJ = np.meshgrid(di, dj, indexing='ij')  # (2r+1, 2r+1)

#     II = i0 + DI
#     JJ = j0 + DJ
#     II = (II + ny) % ny if wrap_lat else np.clip(II, 0, ny-1)
#     JJ = (JJ + nx) % nx if wrap_lon else np.clip(JJ, 0, nx-1)

#     win = mslp[II, JJ]
#     center = mslp[i0, j0]

#     # NaN-safe selection
#     valid = np.isfinite(win)
#     if not np.any(valid):
#         return i0, j0

#     if for_low:
#         # replace invalid with +inf so they won't win
#         w = np.where(valid, win, np.inf)
#         k = int(np.argmin(w))
#         best = float(w.flat[k])
#         if best < center - eps:
#             oi, oj = np.unravel_index(k, win.shape)
#             return int(II[oi, oj]), int(JJ[oi, oj])
#         else:
#             return i0, j0
#     else:
#         # replace invalid with -inf so they won't win
#         w = np.where(valid, win, -np.inf)
#         k = int(np.argmax(w))
#         best = float(w.flat[k])
#         if best > center + eps:
#             oi, oj = np.unravel_index(k, win.shape)
#             return int(II[oi, oj]), int(JJ[oi, oj])
#         else:
#             return i0, j0

def _local_km_scales(lats, lons, iy, ix, wrap_lon=True, wrap_lat=False):
    ny, nx = lats.shape
    im1 = (iy-1+ny)%ny if wrap_lat else max(iy-1, 0)
    ip1 = (iy+1)%ny     if wrap_lat else min(iy+1, ny-1)
    jm1 = (ix-1+nx)%nx if wrap_lon else max(ix-1, 0)
    jp1 = (ix+1)%nx     if wrap_lon else min(ix+1, nx-1)
    dy = haversine_km(lats[im1, ix], lons[im1, ix], lats[ip1, ix], lons[ip1, ix]) / 2.0
    dx = haversine_km(lats[iy, jm1], lons[iy, jm1], lats[iy, jp1], lons[iy, jp1]) / 2.0
    if not np.isfinite(dy) or dy <= 0: dy = 111.0
    if not np.isfinite(dx) or dx <= 0: dx = max(111.0*np.cos(np.radians(lats[iy, ix])), 1e-3)
    return float(dy), float(dx)

def snap_to_extremum_range_km(mslp, lats, lons, iy, ix,
                              for_low=True, range_km=75.0,
                              wrap_lon=True, wrap_lat=False, eps=0.0):
    ny, nx = mslp.shape
    i0, j0 = int(iy), int(ix)

    # convert 75 km to local cell radii
    dy_km, dx_km = _local_km_scales(lats, lons, i0, j0, wrap_lon, wrap_lat)
    ry = int(np.ceil(range_km / max(dy_km, 1e-6)))
    rx = int(np.ceil(range_km / max(dx_km, 1e-6)))

    # rectangular window
    di = np.arange(-ry, ry+1, dtype=int)
    dj = np.arange(-rx, rx+1, dtype=int)
    DI, DJ = np.meshgrid(di, dj, indexing='ij')
    II = (i0 + DI);  JJ = (j0 + DJ)
    II = (II + ny) % ny if wrap_lat else np.clip(II, 0, ny-1)
    JJ = (JJ + nx) % nx if wrap_lon else np.clip(JJ, 0, nx-1)

    # keep only pixels truly within 75 km (ensures circular range)
    dkm = haversine_km(lats[i0, j0], lons[i0, j0], lats[II, JJ], lons[II, JJ])
    mask = (dkm <= (range_km + 1e-6))
    win = mslp[II, JJ]
    valid = np.isfinite(win) & mask
    if not np.any(valid): 
        return i0, j0

    center = float(mslp[i0, j0])
    if for_low:
        w = np.where(valid, win, np.inf)
        k = int(np.argmin(w)); best = float(w.flat[k])
        if best < center - eps:
            oi, oj = np.unravel_index(k, w.shape)
            return int(II[oi, oj]), int(JJ[oi, oj])
        return i0, j0
    else:
        w = np.where(valid, win, -np.inf)
        k = int(np.argmax(w)); best = float(w.flat[k])
        if best > center + eps:
            oi, oj = np.unravel_index(k, w.shape)
            return int(II[oi, oj]), int(JJ[oi, oj])
        return i0, j0

def find_pressure_centers_robust_orography_km(
    mslp_hpa, lats, lons, oro_m,
    wrap_lon=True,
    smooth_km=150,
    prominence_hpa_low_base=2.5,
    prominence_hpa_high_base=4.0,
    prominence_hpa_low_boost=2.5,
    prominence_hpa_high_boost=2.5,
    oro_radius_km=275.0,      # physical window for terrain std
    oro_std_lo_m=50.0,
    oro_std_hi_m=400.0,
    ring_inner_km_low=200,    ring_outer_km_low=600,
    ring_inner_km_high=350,   ring_outer_km_high=1100,
    min_separation_km_low=400,
    min_separation_km_high=700,
    work_dtype=np.float32,
    return_diagnostics=False  # keep big maps only if you need them
):
    """
    Model-agnostic orography-aware MSLP center finder (memory-lean).
    """
    # Cast inputs to float32 (or chosen dtype) to halve memory vs float64
    mslp = np.asarray(mslp_hpa, dtype=work_dtype, order="C")
    oro  = np.asarray(oro_m,    dtype=work_dtype, order="C")
    lat  = np.asarray(lats,     dtype=work_dtype, order="C")
    lon  = np.asarray(lons,     dtype=work_dtype, order="C")

    ny, nx = mslp.shape
    assert oro.shape == (ny, nx) and lat.shape == (ny, nx) and lon.shape == (ny, nx)

    # Grid spacing (km) at domain center
    midy, midx = ny//2, nx//2
    dy_km = haversine_km(lat[midy-1, midx], lon[midy-1, midx],
                         lat[midy+1, midx], lon[midy+1, midx]) / 2.0
    dx_km = haversine_km(lat[midy, (midx-1)%nx], lon[midy, (midx-1)%nx],
                         lat[midy, (midx+1)%nx], lon[midy, (midx+1)%nx]) / 2.0

    # Smoothing sigmas (cells)
    sigma_y = max(0.0, smooth_km / (dy_km * 2.355))
    sigma_x = max(0.0, smooth_km / (dx_km * 2.355))

    # Smooth MSLP (single extra array)
    sm = gaussian_blur2d(mslp, sigma_y, sigma_x, dtype=work_dtype)

    # Terrain std using physical window → anisotropic radii in cells
    ry = max(1, int(round(oro_radius_km / max(dy_km, 1e-6))))
    rx = max(1, int(round(oro_radius_km / max(dx_km, 1e-6))))
    oro_std = local_std_box_aniso(oro, ry, rx)  # one big map

    # Roughness weight w in [0,1] — compute in-place to avoid extra arrays
    w = (oro_std - oro_std_lo_m) / max(oro_std_hi_m - oro_std_lo_m, 1e-6)
    np.clip(w, 0.0, 1.0, out=w)

    # Extrema on smoothed field
    lows_mask, highs_mask = local_extrema_3x3(sm, wrap_lon=wrap_lon)
    low_iy, low_ix   = np.where(lows_mask)
    high_iy, high_ix = np.where(highs_mask)

    # Evaluate candidates with on-the-fly thresholds
    low_cands = []
    for i, j in zip(low_iy, low_ix):
        prom = ring_prominence(sm, lat, lon, int(i), int(j),
                               r_inner_km=ring_inner_km_low, r_outer_km=ring_outer_km_low, for_low=True)
        # prom_req_low = base + boost * w[i,j]
        if prom >= (prominence_hpa_low_base + prominence_hpa_low_boost * float(w[i,j])):
            low_cands.append({"iy": int(i), "ix": int(j), "prom": float(prom), "p": float(mslp[i,j])})

    high_cands = []
    for i, j in zip(high_iy, high_ix):
        prom = ring_prominence(sm, lat, lon, int(i), int(j),
                               r_inner_km=ring_inner_km_high, r_outer_km=ring_outer_km_high, for_low=False)
        if prom >= (prominence_hpa_high_base + prominence_hpa_high_boost * float(w[i,j])):
            high_cands.append({"iy": int(i), "ix": int(j), "prom": float(prom), "p": float(mslp[i,j])})

    # Non-max suppression
    low_kept  = nonmax_separation(low_cands,  lat, lon, min_sep_km=min_separation_km_low)
    high_kept = nonmax_separation(high_cands, lat, lon, min_sep_km=min_separation_km_high)

    # # Results (sorted by prominence)
    # lows = [{"lat": float(lat[c["iy"], c["ix"]]),
    #          "lon": float(lon[c["iy"], c["ix"]]),
    #          "p_hpa": float(mslp[c["iy"], c["ix"]]),
    #          "prom_hpa": float(c["prom"]),
    #          "iy": int(c["iy"]), "ix": int(c["ix"])}
    #         for c in sorted(low_kept, key=lambda x: -x["prom"])]

    # highs = [{"lat": float(lat[c["iy"], c["ix"]]),
    #           "lon": float(lon[c["iy"], c["ix"]]),
    #           "p_hpa": float(mslp[c["iy"], c["ix"]]),
    #           "prom_hpa": float(c["prom"]),
    #           "iy": int(c["iy"]), "ix": int(c["ix"])}
    #          for c in sorted(high_kept, key=lambda x: -x["prom"])]

    # lows = []
    # for c in sorted(low_kept, key=lambda x: -x["prom"]):
    #     iy2, ix2 = snap_to_extremum_window(mslp, c["iy"], c["ix"], for_low=True, wrap_lon=wrap_lon)
    #     lows.append({
    #         "lat": float(lat[iy2, ix2]),
    #         "lon": float(lon[iy2, ix2]),
    #         "p_hpa": float(mslp[iy2, ix2]),  # now the true unsmoothed minimum at snapped location
    #         "iy": iy2, "ix": ix2
    #     })

    # highs = []
    # for c in sorted(high_kept, key=lambda x: -x["prom"]):
    #     iy2, ix2 = snap_to_extremum_window(mslp, c["iy"], c["ix"], for_low=False, wrap_lon=wrap_lon)
    #     highs.append({
    #         "lat": float(lat[iy2, ix2]),
    #         "lon": float(lon[iy2, ix2]),
    #         "p_hpa": float(mslp[iy2, ix2]),
    #         "iy": iy2, "ix": ix2
    #     })

    SNAP_RANGE_KM = 70.0
    
    lows = []
    for c in sorted(low_kept, key=lambda x: -x["prom"]):
        iy2, ix2 = snap_to_extremum_range_km(
            mslp, lat, lon,
            c["iy"], c["ix"],
            for_low=True,
            range_km=SNAP_RANGE_KM,
            wrap_lon=wrap_lon,
            wrap_lat=False
        )
        lows.append({
            "lat": float(lat[iy2, ix2]),
            "lon": float(lon[iy2, ix2]),
            "p_hpa": float(mslp[iy2, ix2]),  # true unsmoothed min at snapped location
            "iy": iy2, "ix": ix2
        })
    
    highs = []
    for c in sorted(high_kept, key=lambda x: -x["prom"]):
        iy2, ix2 = snap_to_extremum_range_km(
            mslp, lat, lon,
            c["iy"], c["ix"],
            for_low=False,
            range_km=SNAP_RANGE_KM,
            wrap_lon=wrap_lon,
            wrap_lat=False
        )
        highs.append({
            "lat": float(lat[iy2, ix2]),
            "lon": float(lon[iy2, ix2]),
            "p_hpa": float(mslp[iy2, ix2]),
            "iy": iy2, "ix": ix2
        })

    if return_diagnostics:
        # Keep maps for inspection (float32)
        return lows, highs, {"oro_std_m": oro_std, "w": w, "sm": sm, "window_cells": (ry, rx)}
    else:
        # Free large maps ASAP; return only essentials
        # (They'll be GC'd when references drop out of scope)
        return lows, highs
