"""Reusable Blender 5.0 animation helpers (slotted Action API)."""
import bpy


def get_fcurves(id_data):
    """Return the ActionChannelbag fcurves collection for an ID's active action slot.

    Blender 5.0 removed Action.fcurves. Path is now:
      id.animation_data.action.layers[0].strips[0].channelbag(slot).fcurves
    """
    ad = id_data.animation_data
    if ad is None or ad.action is None:
        return None
    act = ad.action
    if not act.layers:
        return None
    strip = act.layers[0].strips[0]
    cb = strip.channelbag(ad.action_slot)
    return None if cb is None else cb.fcurves


def find_fcurve(id_data, data_path, index=0):
    fcs = get_fcurves(id_data)
    if fcs is None:
        return None
    for fc in fcs:
        if fc.data_path == data_path and fc.array_index == index:
            return fc
    return None


def set_interp(id_data, data_path, index=0, interpolation='BEZIER', easing='AUTO',
               back=None, amplitude=None, period=None, kf_indices=None):
    """Set interpolation/easing on keyframes of one fcurve."""
    fc = find_fcurve(id_data, data_path, index)
    assert fc is not None, f"no fcurve for {data_path}[{index}]"
    idxs = range(len(fc.keyframe_points)) if kf_indices is None else kf_indices
    for i in idxs:
        kp = fc.keyframe_points[i]
        kp.interpolation = interpolation
        kp.easing = easing
        if back is not None:
            kp.back = back
        if amplitude is not None:
            kp.amplitude = amplitude
        if period is not None:
            kp.period = period
    fc.update()
    return fc


def cubic_bezier_ease(fc, i, p1=(0.25, 0.1), p2=(0.25, 1.0)):
    """Impose a CSS-style cubic-bezier(p1x,p1y,p2x,p2y) on segment i -> i+1.

    Sets FREE handles at the exact numeric positions implied by the control
    points, in (frame, value) space. This gives a genuine custom ease rather
    than Blender's AUTO_CLAMPED default.
    """
    a = fc.keyframe_points[i]
    b = fc.keyframe_points[i + 1]
    x0, y0 = a.co
    x1, y1 = b.co
    dx, dy = (x1 - x0), (y1 - y0)

    a.interpolation = 'BEZIER'
    a.handle_right_type = 'FREE'
    b.handle_left_type = 'FREE'
    a.handle_right = (x0 + dx * p1[0], y0 + dy * p1[1])
    b.handle_left = (x0 + dx * p2[0], y0 + dy * p2[1])
    fc.update()
    return a.handle_right[:], b.handle_left[:]
