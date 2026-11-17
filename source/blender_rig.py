"""Blender: split the head collection, trim backs, add face shape keys, export one GLB.
Coordinates below are in 'game space' (x right, y up, z toward the viewer)."""
import bpy, bmesh, math, sys
from mathutils import Vector

SRC = '/home/claude/models2/coll.fbx'
OUT = sys.argv[sys.argv.index('--') + 1] if '--' in sys.argv else '/home/claude/models2/heads.glb'

# face landmarks (game space, measured from front renders)
HEADS = {
  'robot':   dict(cx=-0.335, mouth=None,
                  eyes=[], brows=None),
  'bigfoot': dict(cx=-0.115, mouth=dict(x=-0.115, w=0.066, up=0.172, lo=0.140, chin=0.06, jaw=0.32, split=0.1325, smile=0.011),
                  eyes=[(-0.150, 0.225, 0.017, 0.009), (-0.084, 0.222, 0.017, 0.009)],
                  brows=dict(y=0.243, xs=(-0.150, -0.084), rx=0.022, ry=0.009, up=0.006)),
  'chipmunk':dict(cx=0.133, mouth=dict(x=0.133, w=0.062, up=0.118, lo=0.075, chin=0.045, jaw=0.34, xf=3.2),
                  eyes=[(0.077, 0.183, 0.032, 0.03), (0.19, 0.183, 0.032, 0.03)],
                  brows=dict(y=0.212, xs=(0.077, 0.19), rx=0.035, ry=0.012, up=0.007)),
  'alien':   dict(cx=0.383, mouth=dict(x=0.385, w=0.056, up=0.106, lo=0.067, chin=0.035, jaw=0.32),
                  eyes=[(0.315, 0.198, 0.052, 0.036), (0.448, 0.198, 0.052, 0.036)],
                  brows=dict(y=0.236, xs=(0.315, 0.448), rx=0.05, ry=0.012, up=0.006), blink=0.55),
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
for o in parts:
    c = sum((G(v.co)[0] for v in o.data.vertices)) / max(1, len(o.data.vertices))
    k = min(HEADS, key=lambda h: abs(HEADS[h]['cx'] - c)); groups[k].append(o)
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
    kill = [f for f in bm.faces if all(G(v.co)[2] < zmid - 0.01 for v in f.verts)]
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
    Ac = math.asin(min(0.9, (M['up'] - M['lo'] - 0.003) / Rl)); cc, sc = math.cos(Ac), math.sin(Ac)
    report[k]['zf'] = round(zf, 4)

    ob.shape_key_add(name='Basis')
    keys = {n: ob.shape_key_add(name=n, from_mix=False) for n in ('close', 'jaw', 'wide', 'round', 'brow', 'blink')}
    for i, (x, y, z) in enumerate(gv):
        d = {n: [0.0, 0.0, 0.0] for n in keys}
        ax = abs(x - M['x'])
        lipx = ss(M['w'] * 1.45, M['w'] * 0.9, ax)
        front = ss(zf - 0.045, zf - 0.012, z)
        # one solid jaw: everything below the split line swings around the hinge.
        #   'jaw'   opens it (down), 'close' swings it up until the lower lip meets the upper lip
        sp = split + M.get('smile', 0) * min(1.0, (ax / M['w']) ** 2)
        if y < sp + 0.003:
            xf = M.get('xf', 2.1)
            wj = ss(M['w'] * xf, M['w'] * 1.2, ax) * ss(zf - 0.16, zf - 0.085, z) * ss(sp + 0.003, sp - 0.003, y)
            ry, rz = y - piv[1], z - piv[2]
            d['jaw'][1] = (ry * ca - rz * sa - ry) * wj
            d['jaw'][2] = (ry * sa + rz * ca - rz) * wj
            d['close'][1] = (ry * cc + rz * sc - ry) * wj
            d['close'][2] = (-ry * sc + rz * cc - rz) * wj
        # lips wide (ee) and round (oo)
        ey = (y - my) / ((M['up'] - M['lo']) * 1.6)
        wl2 = ss(1.0, 0.5, math.hypot((x - M['x']) / (M['w'] * 1.5), ey)) * ss(zf - 0.05, zf - 0.015, z)
        d['wide'][0] = (x - M['x']) * 0.28 * wl2
        d['wide'][1] = 0.004 * min(1, ax / M['w']) * wl2
        d['round'][0] = -(x - M['x']) * 0.42 * wl2
        d['round'][1] = (my - y) * 0.25 * wl2
        d['round'][2] = 0.008 * wl2 * (1 - min(1, ax / M['w']))
        # brows
        Bw = H['brows']
        for bx in Bw['xs']:
            r = math.hypot((x - bx) / Bw['rx'], (y - Bw['y']) / Bw['ry'])
            d['brow'][1] += Bw['up'] * ss(1.7, 0.6, r) * ss(zf - 0.08, zf - 0.03, z) if False else Bw['up'] * ss(1.7, 0.6, r)
        # eyelids: squash each eye toward its lid line
        for (ex, ey0, rx, ry) in H['eyes']:
            r = math.hypot((x - ex) / rx, (y - ey0) / ry)
            we = ss(1.35, 0.85, r) * H.get('blink', 1.0)
            if we > 0:
                y0 = ey0 - ry * 0.25
                d['blink'][1] += (y0 - y) * 0.95 * we
                d['blink'][2] += 0.0015 * we
        base = me.vertices[i].co
        for n, kb in keys.items():
            dx, dy, dz = d[n]
            kb.data[i].co = base + Vector((dx, -dz, dy))

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
