"""
Parameterized Heat Sink STL Generator
======================================
Generates an STL file for a rectangular plate-fin heat sink.

Geometry layout:
  - X axis: flow direction (length)
  - Y axis: vertical (base thickness + fin height)
  - Z axis: width (fins are distributed along this axis)

  Heat source is at y = 0 (bottom of base plate).
  Air flows in the +X direction between the fins.
"""

import numpy as np
from stl import mesh
from stl.stl import Mode as StlMode
import argparse
import sys

# ── Default Parameters (all in metres) ───────────────────────────────────────
DEFAULTS = {
    "L":      0.060,   # Base plate length (flow direction)
    "W":      0.060,   # Base plate width
    "H_base": 0.003,   # Base plate thickness
    "N_fin":  5,        # Number of fins
    "H_fin":  0.020,   # Fin height
    "t_fin":  0.002,   # Fin thickness
}


def make_box(x0, y0, z0, x1, y1, z1):
    """
    Create 12 triangular facets for an axis-aligned box.

    Parameters
    ----------
    x0, y0, z0 : float – min corner
    x1, y1, z1 : float – max corner

    Returns
    -------
    np.ndarray of shape (12, 3, 3) – vertices of 12 triangles
    """
    # 8 vertices
    v = np.array([
        [x0, y0, z0],  # 0
        [x1, y0, z0],  # 1
        [x1, y1, z0],  # 2
        [x0, y1, z0],  # 3
        [x0, y0, z1],  # 4
        [x1, y0, z1],  # 5
        [x1, y1, z1],  # 6
        [x0, y1, z1],  # 7
    ])

    # 12 triangles (2 per face, outward normals via right-hand rule)
    faces = np.array([
        # Bottom (y = y0)
        [0, 1, 5], [0, 5, 4],
        # Top (y = y1)
        [2, 3, 7], [2, 7, 6],
        # Front (z = z0)
        [0, 3, 2], [0, 2, 1],
        # Back (z = z1)
        [4, 5, 6], [4, 6, 7],
        # Left (x = x0)
        [0, 4, 7], [0, 7, 3],
        # Right (x = x1)
        [1, 2, 6], [1, 6, 5],
    ])

    triangles = np.zeros((12, 3, 3))
    for i, face in enumerate(faces):
        triangles[i] = v[face]

    return triangles


def generate_heatsink(L, W, H_base, N_fin, H_fin, t_fin, base_extension=0.001):
    """
    Generate the heat sink as a combined STL mesh.

    Parameters
    ----------
    base_extension : float
        Distance (m) the base extends below y=0. This ensures the STL
        protrudes through the domain floor so snappyHexMesh cleanly
        removes cells inside the heatsink. Default 1 mm.

    Returns
    -------
    stl.mesh.Mesh
    dict with computed parameters
    """
    # Fin spacing
    s = (W - N_fin * t_fin) / (N_fin + 1)
    if s <= 0:
        raise ValueError(
            f"Fins don't fit: W={W*1000:.1f}mm, N_fin={N_fin}, "
            f"t_fin={t_fin*1000:.1f}mm → spacing={s*1000:.2f}mm"
        )

    info = {
        "fin_spacing_mm": s * 1000,
        "total_fin_volume_mm3": N_fin * t_fin * L * H_fin * 1e9,
        "base_volume_mm3": L * W * H_base * 1e9,
        "total_solid_volume_mm3": (L * W * H_base + N_fin * t_fin * L * H_fin) * 1e9,
    }

    all_triangles = []

    # ── Base plate ────────────────────────────────────────────────────────
    # Extend base below y=0 for clean snappyHexMesh intersection with floor
    base = make_box(0, -base_extension, 0, L, H_base, W)
    all_triangles.append(base)

    # ── Fins ──────────────────────────────────────────────────────────────
    for i in range(N_fin):
        z_start = s + i * (t_fin + s)
        z_end = z_start + t_fin

        fin = make_box(0, H_base, z_start, L, H_base + H_fin, z_end)
        all_triangles.append(fin)

    # ── Combine into single mesh ──────────────────────────────────────────
    all_triangles = np.concatenate(all_triangles, axis=0)
    n_facets = all_triangles.shape[0]

    heatsink = mesh.Mesh(np.zeros(n_facets, dtype=mesh.Mesh.dtype))
    for i in range(n_facets):
        heatsink.vectors[i] = all_triangles[i]

    return heatsink, info


def visualize(stl_path):
    """Show the STL using PyVista."""
    try:
        import pyvista as pv
    except ImportError:
        print("PyVista not installed — skipping visualization.")
        print("Install with: pip install pyvista")
        return

    reader = pv.STLReader(stl_path)
    stl_mesh = reader.read()

    plotter = pv.Plotter()
    plotter.add_mesh(stl_mesh, color="silver", show_edges=True, edge_color="gray")
    plotter.add_axes()
    plotter.add_text(
        "Heat Sink STL\nX: flow direction | Y: height | Z: width",
        position="upper_left", font_size=10
    )
    plotter.show_grid()
    plotter.view_isometric()
    plotter.show()


def main():
    parser = argparse.ArgumentParser(description="Generate heat sink STL")
    parser.add_argument("--length",    type=float, default=DEFAULTS["L"],      help="Base length [m]")
    parser.add_argument("--width",     type=float, default=DEFAULTS["W"],      help="Base width [m]")
    parser.add_argument("--base-height", type=float, default=DEFAULTS["H_base"], help="Base thickness [m]")
    parser.add_argument("--n-fins",    type=int,   default=DEFAULTS["N_fin"],  help="Number of fins")
    parser.add_argument("--fin-height", type=float, default=DEFAULTS["H_fin"], help="Fin height [m]")
    parser.add_argument("--fin-thickness", type=float, default=DEFAULTS["t_fin"], help="Fin thickness [m]")
    parser.add_argument("--base-extension", type=float, default=0.001, help="Base extension below y=0 for meshing [m]")
    parser.add_argument("--output",    type=str,   default="heatsink.stl",     help="Output STL file")
    parser.add_argument("--show",      action="store_true",                     help="Show 3D visualization")
    parser.add_argument("--save-image", type=str,  default=None,               help="Save screenshot to file")
    args = parser.parse_args()

    print("=" * 60)
    print("  Heat Sink STL Generator")
    print("=" * 60)
    print(f"  Base:  {args.length*1000:.1f} x {args.width*1000:.1f} x {args.base_height*1000:.1f} mm")
    print(f"  Fins:  {args.n_fins} fins, {args.fin_height*1000:.1f} mm tall, {args.fin_thickness*1000:.1f} mm thick")

    heatsink, info = generate_heatsink(
        args.length, args.width, args.base_height,
        args.n_fins, args.fin_height, args.fin_thickness,
        base_extension=args.base_extension
    )

    print(f"  Fin spacing: {info['fin_spacing_mm']:.2f} mm")
    print(f"  Total solid volume: {info['total_solid_volume_mm3']:.1f} mm³")
    print(f"  Facets: {len(heatsink.vectors)}")
    print(f"  Output: {args.output}")

    # Save as ASCII with a clean solid name for snappyHexMesh surface referencing
    heatsink.save(args.output, mode=StlMode.ASCII)

    # numpy-stl writes an auto-generated name; replace with a clean solid name
    with open(args.output, "r") as f:
        content = f.read()
    # Replace first 'solid ...' line and matching 'endsolid ...' line
    lines = content.splitlines(keepends=True)
    lines[0] = "solid heatsink\n"
    lines[-1] = "endsolid heatsink\n"
    with open(args.output, "w") as f:
        f.writelines(lines)

    print("  ✓ STL saved successfully (ASCII, solid name: 'heatsink')")

    if args.save_image:
        save_screenshot(args.output, args.save_image)

    if args.show:
        visualize(args.output)

    print("=" * 60)
    return info


def save_screenshot(stl_path, image_path):
    """Save an off-screen screenshot of the STL."""
    try:
        import pyvista as pv
    except ImportError:
        print("  PyVista not installed — skipping screenshot.")
        return

    pv.OFF_SCREEN = True
    reader = pv.STLReader(stl_path)
    stl_mesh = reader.read()

    plotter = pv.Plotter(off_screen=True, window_size=[1200, 800])
    plotter.add_mesh(stl_mesh, color="silver", show_edges=True, edge_color="gray")
    plotter.add_axes()
    plotter.add_text(
        "Heat Sink STL\nX: flow | Y: height | Z: width",
        position="upper_left", font_size=10
    )
    plotter.show_grid()
    plotter.view_isometric()
    plotter.screenshot(image_path)
    print(f"  ✓ Screenshot saved: {image_path}")


if __name__ == "__main__":
    main()
