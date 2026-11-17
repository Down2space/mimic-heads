"""Blender: split the head collection, trim backs, add face shape keys, export one GLB.
Coordinates below are in 'game space' (x right, y up, z toward the viewer)."""
import bpy, bmesh, math, sys, json
TEETH = json.load(open('/home/claude/models2/teeth.json'))
from mathutils import Vector

SRC = '/home/claude/models2/coll.fbx'
OUT = sys.argv[sys.argv.index('--') + 1] if '--' in sys.argv else '/home/claude/models2/heads.glb'

# face landmarks (game space, measured from front renders)
HEADS = {
  'robot':   dict(cx=-0.335, mouth=None,
                  eyes=[], brows=None),
  'bigfoot': dict(cx=-0.115, mouth=dict(x=-0.115, w=0.066, up=0.172, lo=0.140, chin=0.06, jaw=0.32, split=0.1325, smile=0.011, tuck=0.016, lofwd=0.012, updrop=0.005),
                  eyes=[(-0.150, 0.225, 0.017, 0.009), (-0.084, 0.222, 0.017, 0.009)],
                  brows=dict(y=0.243, xs=(-0.150, -0.084), rx=0.022, ry=0.009, up=0.006)),
  'chipmunk':dict(cx=0.133, mouth=dict(x=0.133, w=0.062, up=0.118, lo=0.075, chin=0.045, jaw=0.34, xf=3.2, updrop=0.004, lofwd=0.02, over=0.012),
                  eyes=[(0.077, 0.183, 0.032, 0.03), (0.19, 0.183, 0.032, 0.03)],
                  brows=dict(y=0.212, xs=(0.077, 0.19), rx=0.035, ry=0.012, up=0.007), blink=0.0),
  'alien':   dict(cx=0.383, mouth=dict(x=0.385, w=0.056, up=0.106, lo=0.067, chin=0.035, jaw=0.32),
                  eyes=[(0.315, 0.198, 0.052, 0.036), (0.448, 0.198, 0.052, 0.036)],
                  brows=dict(y=0.236, xs=(0.315, 0.448), rx=0.05, ry=0.012, up=0.006), blink=0.0),
}

def ss(a, b, x):
    t = (x - a) / (b - a); t = 0.0 if t < 0 else 1.0 if t > 1 else t
    return t * t * (3 - 2 * t)

# game <-> blender:  game(x,y,z) = blender(x, z, -y)
G = lambda v: (v.x, v.z, -v.y)
B = lambda x, y, z: Vector((x, -z, y))

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.fbx(filepath=SRC)
src = [o for o in bpy.context.scene.objects if o.type == 'MESH'][0]
bpy.context.view_layer.objects.active = src
src.select_set(True)
bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
for o in list(bpy.context.scene.objects):
    if o.type != 'MESH': bpy.data.objects.remove(o)

# weld duplicate verts so the surface deforms as one piece
bm = bmesh.new(); bm.from_mesh(src.data)
bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-6)
bm.to_mesh(src.data); bm.free()

# split into heads: each connected piece goes to the nearest head centre
bpy.ops.object.mode_set(mode='EDIT'); bpy.ops.mesh.select_all(action='SELECT')
bpy.ops.mesh.separate(type='LOOSE'); bpy.ops.object.mode_set(mode='OBJECT')
parts = [o for o in bpy.context.scene.objects if o.type == 'MESH']
groups = {k: [] for k in HEADS}
EYEBOX = {}
for o in parts:
    P = [G(v.co) for v in o.data.vertices]; n = len(P)
    c = [sum(p[i] for p in P) / n for i in range(3)]
    lo = [min(p[i] for p in P) for i in range(3)]; hi = [max(p[i] for p in P) for i in range(3)]
    k = min(HEADS, key=lambda h: abs(HEADS[h]['cx'] - c[0]))
    H = HEADS[k]; M = H['mouth']; tag = None
    if n <= 22 and c[1] > 0.235 and k != 'robot':
        bpy.data.objects.remove(o); continue          # stray hair tufts (showed up as red spikes)
    if M and n < 300 and abs(c[0] - M['x']) < M['w'] and M['lo'] - 0.035 < c[1] < M['up'] + 0.012:
        tag = 'teeth_up' if c[1] > M.get('split', M['lo'] + 0.006) else 'teeth_lo'
    elif n < 120 and H['eyes'] and min(math.hypot(c[0] - ex, c[1] - ey) for ex, ey, _, _ in H['eyes']) < 0.045:
        tag = 'eyeball'; EYEBOX.setdefault(k, []).append(((lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2, (hi[0] - lo[0]) / 2, (hi[1] - lo[1]) / 2))
    if tag:
        vg = o.vertex_groups.new(name=tag); vg.add(list(range(n)), 1.0, 'REPLACE')
    groups[k].append(o)
heads = {}
for k, objs in groups.items():
    bpy.ops.object.select_all(action='DESELECT')
    for o in objs: o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    if len(objs) > 1: bpy.ops.object.join()
    ob = bpy.context.view_layer.objects.active; ob.name = k; ob.data.name = k
    heads[k] = ob

report = {}
for k, ob in heads.items():
    me = ob.data; H = HEADS[k]
    gv = [G(v.co) for v in me.vertices]
    zs = [p[2] for p in gv]; zmid = (min(zs) + max(zs)) / 2
    # trim the back: drop faces entirely behind the middle of the head
    bm = bmesh.new(); bm.from_mesh(me)
    kill = [f for f in bm.faces if all(G(v.co)[2] < zmid - 0.01 and G(v.co)[1] > 0.06 for v in f.verts)]
    bmesh.ops.delete(bm, geom=kill, context='FACES')
    loose = [v for v in bm.verts if not v.link_faces]
    bmesh.ops.delete(bm, geom=loose, context='VERTS')
    bm.to_mesh(me); bm.free()
    gv = [G(v.co) for v in me.vertices]
    report[k] = dict(tris=sum(len(p.vertices) - 2 for p in me.polygons), verts=len(me.vertices))
    if not H['mouth']:
        continue
    M = H['mouth']; my = (M['up'] + M['lo']) / 2
    near = [p for p in gv if abs(p[0] - M['x']) < M['w'] * 1.2 and M['lo'] - 0.015 < p[1] < M['up'] + 0.015]
    zf = max(p[2] for p in near)          # front of the lips
    piv = (M['x'], my + 0.012, zf - 0.11)  # jaw hinge, behind the mouth
    A = M['jaw']; ca, sa = math.cos(A), math.sin(A)
    split = M.get('split', M['lo'] + 0.006)
    # how far up the jaw must swing for the lower lip to reach the upper lip
    Rl = math.hypot(M['lo'] - piv[1], zf - piv[2])
    Ac = math.asin(min(0.9, (M['up'] - M['lo'] + M.get('over', 0.0)) / Rl)); cc, sc = math.cos(Ac), math.sin(Ac)
    report[k]['zf'] = round(zf, 4)

    ob.shape_key_add(name='Basis')
    keys = {n: ob.shape_key_add(name=n, from_mix=False) for n in ('close', 'jaw', 'wide', 'round', 'brow', 'blink')}
    nv = len(gv)
    # neighbours, for smoothing weights across the surface
    nb = [[] for _ in range(nv)]
    for e in me.edges:
        a_, b_ = e.vertices; nb[a_].append(b_); nb[b_].append(a_)
    def smooth(w, pin, it=10, lam=0.6):
        w = list(w)
        for _ in range(it):
            nw = w[:]
            for i in range(nv):
                if pin[i] or not nb[i]: continue
                avg = sum(w[j] for j in nb[i]) / len(nb[i])
                nw[i] = w[i] + lam * (avg - w[i])
            w = nw
        return w
    def in_group(name):
        g = ob.vertex_groups.get(name)
        if not g: return [False] * nv
        return [any(gg.group == g.index for gg in v.groups) for v in me.vertices]
    T_UP, T_LO, EYEB = in_group('teeth_up'), in_group('teeth_lo'), in_group('eyeball')
    eyes = EYEBOX.get(k) or H['eyes']
    TE = set(tuple(round(c, 4) for c in p) for p in TEETH.get(k, []))
    is_tooth = [(tuple(round(c, 4) for c in p) in TE) or T_UP[i] or T_LO[i] for i, p in enumerate(gv)]
    # raw weights
    wj = [0.0] * nv; wl = [0.0] * nv; pin = [False] * nv; upl = [0.0] * nv; lol = [0.0] * nv
    for i, (x, y, z) in enumerate(gv):
        ax = abs(x - M['x'])
        sp = split + M.get('smile', 0) * min(1.0, (ax / M['w']) ** 2)
        xf = M.get('xf', 2.1)
        if y < sp + 0.003:
            wj[i] = ss(M['w'] * xf, M['w'] * 1.2, ax) * ss(zf - 0.16, zf - 0.085, z) * ss(sp + 0.003, sp - 0.003, y)
        # keep the lip rim crisp: pin vertices right at the mouth opening
        if ax < M['w'] * 1.05 and abs(y - sp) < 0.01 and z > zf - 0.05: pin[i] = True
        ey = (y - my) / ((M['up'] - M['lo']) * 1.1)
        wl[i] = ss(1.0, 0.4, math.hypot((x - M['x']) / (M['w'] * 1.9), ey)) * ss(zf - 0.05, zf - 0.015, z)
        # keep the pucker on the lips: fade out above the upper lip and below the lower lip
        if y > M['up']: wl[i] *= ss(M['up'] + 0.014, M['up'], y)
        if y < M['lo']: wl[i] *= ss(M['lo'] - 0.022, M['lo'], y)
        front = ss(zf - 0.03, zf - 0.008, z) * ss(M['w'] * 1.3, M['w'] * 0.8, ax)
        if y >= sp and not is_tooth[i]: upl[i] = front * ss(M['up'] + 0.022, M['up'], y)
        if y < sp and not is_tooth[i]: lol[i] = front * ss(M['lo'] - 0.03, M['lo'], y)
    # protect the teeth: nothing between the lip lines (away from the corners) gets squeezed
    band = [(M['lo'] + 0.002 < gv[i][1] < M['up'] - 0.002 and abs(gv[i][0] - M['x']) < M['w'] * 0.85 and gv[i][2] < zf + 0.01) or is_tooth[i] for i in range(nv)]
    wl = [0.0 if band[i] else wl[i] for i in range(nv)]
    tm = smooth([1.0 if t else 0.0 for t in is_tooth], [False] * nv, 3, 0.6)
    wj = smooth(wj, [p or T_UP[i] or T_LO[i] for i, p in enumerate(pin)])
    for i in range(nv):
        if T_LO[i]: wj[i] = 1.0
        if T_UP[i] or EYEB[i]: wj[i] = 0.0
    wl = smooth(wl, band, 6, 0.5)
    wl = [wl[i] * (1 - min(1.0, tm[i] * 1.8)) for i in range(nv)]
    upl = smooth(upl, [False] * nv, 4, 0.5); lol = smooth(lol, [False] * nv, 4, 0.5)
    sp0 = lambda x: split + M.get('smile', 0) * min(1.0, (abs(x - M['x']) / M['w']) ** 2)
    tw = [1.0 if (is_tooth[i] and gv[i][1] >= sp0(gv[i][0]) - 0.002) else 0.0 for i in range(nv)]
    upper = [gv[i][1] >= sp0(gv[i][0]) for i in range(nv)]
    tw = smooth(tw, [False] * nv, 8, 0.6)
    tw = [min(1.0, t * 1.6) if upper[i] else 0.0 for i, t in enumerate(tw)]
    tw = [1.0 if T_UP[i] else (0.0 if T_LO[i] else tw[i]) for i in range(nv)]
    tuck = M.get('tuck', 0.0)
    for i, (x, y, z) in enumerate(gv):
        d = {n: [0.0, 0.0, 0.0] for n in keys}
        ax = abs(x - M['x'])
        ry, rz = y - piv[1], z - piv[2]
        w = wj[i]
        d['jaw'][1] = (ry * ca - rz * sa - ry) * w
        d['jaw'][2] = (ry * sa + rz * ca - rz) * w
        d['close'][1] = (ry * cc + rz * sc - ry) * w
        d['close'][2] = (-ry * sc + rz * cc - rz) * w
        # lips meet: upper lip drops a little, lower lip comes forward over big teeth
        d['close'][1] += -M.get('updrop', 0.002) * upl[i]
        d['close'][2] += M.get('lofwd', 0.0) * lol[i]
        # big front teeth tuck back under the upper lip when the mouth shuts
        if tuck > 0 and tw[i] > 0:
            d['close'][2] += -tuck * tw[i]; d['close'][1] += tuck * 0.35 * tw[i]
        # lips wide (ee) and round (oo)
        d['wide'][0] = (x - M['x']) * 0.22 * wl[i]
        d['wide'][1] = 0.004 * min(1, ax / M['w']) * wl[i]
        d['round'][0] = -(x - M['x']) * 0.85 * wl[i]
        d['round'][1] = (my - y) * 0.14 * wl[i]
        d['round'][2] = 0.013 * wl[i] * (1 - min(1, ax / M['w']) ** 2)
        Bw = H['brows']
        for bx in Bw['xs']:
            r = math.hypot((x - bx) / Bw['rx'], (y - Bw['y']) / Bw['ry'])
            d['brow'][1] += Bw['up'] * ss(1.7, 0.6, r)
        if not EYEB[i] and H.get('blink', 1.0) > 0:
            for (ex, ey0, rx, ry_) in eyes:
                ylid = ey0 - ry_ * 0.55
                if y <= ylid: continue
                r = math.hypot((x - ex) / (rx * 1.1), (y - ey0) / (ry_ * 1.1))
                fy = ss(ey0 - ry_ * 0.35, ey0 + ry_ * 0.5, y)
                wlid = ss(1.55, 1.0, r) * fy * H.get('blink', 1.0)
                if wlid > 0:
                    d['blink'][1] += max(ylid - y, -ry_ * 1.6) * wlid
                    d['blink'][2] += 0.004 * wlid
        base = me.vertices[i].co
        for n, kb in keys.items():
            dx, dy, dz = d[n]
            kb.data[i].co = base + Vector((dx, -dz, dy))

img0 = bpy.data.images[0]; W0, H0 = img0.size; PX = img0.pixels[:]
def texcol(u, v):
    x = min(W0 - 1, max(0, int(u * (W0 - 1)))); y = min(H0 - 1, max(0, int(v * (H0 - 1)))); o = (y * W0 + x) * 4
    return PX[o], PX[o + 1], PX[o + 2]
fixed = {}
for k, ob in heads.items():
    me = ob.data; uvl = me.uv_layers.active.data; n = 0
    loops_by_v = {}
    for li, l in enumerate(me.loops): loops_by_v.setdefault(l.vertex_index, []).append(li)
    def red(li):
        r, g, b = texcol(*uvl[li].uv)
        if k == 'chipmunk' and G(me.vertices[me.loops[li].vertex_index].co)[1] > 0.25:
            return r > 0.4 and r > g * 1.5 and r > b * 1.5
        return r > 0.55 and r > g * 2.2 and r > b * 2.2
    for p in me.polygons:
        lis = list(p.loop_indices); bad = [li for li in lis if red(li)]
        good = [li for li in lis if not red(li)]
        if bad and good:
            for li in bad: uvl[li].uv = uvl[good[0]].uv.copy(); n += 1
    fixed[k] = n
print('RED_FIXED', fixed)

# one shared, smaller texture for the watch
for img in bpy.data.images:
    if img.size[0] > 1024:
        img.scale(1536, 1536)

for o in bpy.context.scene.objects: o.select_set(o.name in heads)
bpy.ops.export_scene.gltf(filepath=OUT, export_format='GLB', use_selection=True,
    export_morph=True, export_morph_normal=False, export_image_format='JPEG', export_jpeg_quality=80,
    export_apply=False, export_yup=True, export_texcoords=True, export_normals=True,
    export_materials='EXPORT', export_animations=False)
import json; print('REPORT', json.dumps(report))
