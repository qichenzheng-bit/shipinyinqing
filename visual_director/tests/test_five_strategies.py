"""Smoke tests for the five visual strategies, never new mathematical solutions."""
from visual_director import build_storyboard, DirectorOptions, DiagramSpec, DiagramPoint, DiagramLine


def test_calculation_layout(teacher_package):
    package=build_storyboard(teacher_package)
    assert next(s.layout for s in package.scenes if s.event_id=="e_d_log")=="full_board"


def test_matrix_comparison_layout(teacher_package):
    source=next(o for o in teacher_package["lesson"]["math_objects"] if o["math_object_id"]=="m_common")
    source["latex"]=r"\begin{pmatrix}1&2\\2&5\end{pmatrix}"
    board=build_storyboard(teacher_package)
    assert next(s.layout for s in board.scenes if s.event_id=="e_common")=="matrix_compare"


def test_long_proof_layout(teacher_package):
    next(e for e in teacher_package["plan"]["teaching_events"] if e["event_id"]=="e_d_log")["event_type"]="proof"
    board=build_storyboard(teacher_package)
    assert next(s.layout for s in board.scenes if s.event_id=="e_d_log")=="proof_scroll"


def test_explicit_geometry_layout(teacher_package):
    geometry=DiagramSpec(event_id="e_d_log",points=[DiagramPoint(id="P",x=.25,y=.4,label="P"),DiagramPoint(id="Q",x=.75,y=.65,label="Q")],lines=[DiagramLine(id="PQ",start="P",end="Q")])
    board=build_storyboard(teacher_package,DirectorOptions(diagrams=[geometry]))
    assert next(s for s in board.scenes if s.event_id=="e_d_log").diagram.labels


def test_probability_needs_explicit_diagram_to_use_graphic_layout(teacher_package):
    teacher_package["understanding"]["problem_understanding"]["problem_type"]="probability"
    assert all(scene.layout!="diagram_split" for scene in build_storyboard(teacher_package).scenes)
    d=DiagramSpec(event_id="e_d_log",points=[DiagramPoint(id="t",x=.5,y=.5,label="t")])
    board=build_storyboard(teacher_package,DirectorOptions(diagrams=[d]))
    assert next(s.layout for s in board.scenes if s.event_id=="e_d_log")=="diagram_split"