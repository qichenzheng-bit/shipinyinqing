"""Project CRUD/batch trash tests preserving individual deletion intentions."""
from fastapi.testclient import TestClient
from weiguang_backend.main import create_app
from weiguang_backend.models import Job


def _lesson(client,title,project_id):
    res=client.post("/api/v1/lessons",json={
        "title":title,"problem":"计算 1+1。",
        "reference_solution":"结果为 2。","project_id":project_id,
    })
    assert res.status_code==201,res.text
    return res.json()["id"]


def test_project_crud_batch_delete_preserves_individually_deleted(tmp_path):
    client=TestClient(create_app(
        data_dir=tmp_path,local_dev=True,eager=True,
    ))
    pids=[]
    for title in ["第一组","第二组"]:
        res=client.post("/api/v1/projects",json={"title":title})
        assert res.status_code==201
        pids.append(res.json()["id"])
    name=client.patch("/api/v1/projects/"+pids[0],
        json={"title":"考研数学项目"})
    assert name.status_code==200
    active=_lesson(client,"积分",pids[0])
    already_trashed=_lesson(client,"原先删除的题",pids[0])
    second=_lesson(client,"极限",pids[1])
    removed=client.delete("/api/v1/lessons/"+already_trashed)
    assert removed.status_code==200
    failed=client.post("/api/v1/projects/batch-delete",json={
        "ids":[pids[0],"missing"],
    })
    assert failed.status_code==404
    assert len(client.get("/api/v1/projects").json())==2
    result=client.post("/api/v1/projects/batch-delete",json={"ids":pids})
    assert result.status_code==200,result.text
    assert result.json()["lessons_affected"]==2
    assert client.get("/api/v1/projects").json()==[]
    assert len(client.get("/api/v1/projects/trash").json())==2
    assert len(client.get("/api/v1/trash").json())==3
    forbidden=client.post("/api/v1/trash/restore",json={
        "ids":[active],
    })
    assert forbidden.status_code==409
    restored=client.post("/api/v1/projects/restore",json={"ids":pids})
    assert restored.status_code==200
    assert restored.json()["lessons_restored"]==2
    ids={x["id"] for x in client.get("/api/v1/lessons").json()}
    assert ids=={active,second}
    assert client.get("/api/v1/lessons/"+already_trashed).status_code==404
    assert client.post("/api/v1/trash/restore",json={
        "ids":[already_trashed],
    }).status_code==200


def test_project_batch_delete_is_blocked_by_active_video_task(tmp_path):
    app=create_app(data_dir=tmp_path,local_dev=True,eager=True)
    client=TestClient(app)
    project=client.post("/api/v1/projects",json={"title":"工作中"}).json()["id"]
    lesson=_lesson(client,"当前任务",project)
    with app.state.SessionLocal() as db:
        db.add(Job(lesson_id=lesson,kind="render",status="running"))
        db.commit()
    res=client.post("/api/v1/projects/batch-delete",json={"ids":[project]})
    assert res.status_code==409
    assert len(client.get("/api/v1/projects").json())==1
