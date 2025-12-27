from fastapi import FastAPI, UploadFile, File, Request, Form, BackgroundTasks, Query, HTTPException
from pydantic import BaseModel
from typing import Optional
import uvicorn
import time
import httpx
import asyncio
from concurrent.futures import ThreadPoolExecutor


# 创建 FastAPI 实例
app = FastAPI(servers=[{"url": "http://your_localhost_ip:6065"}])


# 任务函数 可替换为 算法/项目 执行部分
def run_long_test(name: str):
    try:
        print("开始执行 ... ...")
        time.sleep(60)
        response_hello = f"Hello, {name}."
        print("Done.")

        return response_hello, True  # 返回任务的结果 和 状态

    except Exception as e:
        error_msg = str(e)
        return error_msg, False


# 定义任务的结果返回函数
async def post_result(sciminer_request_ip: str, sciminer_task_id: str, sciminer_task_type: str, result_msg: str, task_success: bool):

    async with httpx.AsyncClient() as client:

        if task_success:
            task_status = "SUCCESS"
            
        else:
            task_status = "FAILURE"


        data = {
            "sciminer_task_id": sciminer_task_id,
            "task_type": sciminer_task_type,
            "result": result_msg,
            "status": task_status
        }

        print("sciminer_request_ip:", sciminer_request_ip)
        print("sciminer_task_id:", sciminer_task_id)

        post_state_url = f"{sciminer_request_ip}/console/api/custom_api/update"

        response = await client.post(post_state_url, json=data)
        response_status = response.status_code
        response_text = response.text

        print(f"Response Status: {response_status}")
        print(f"Response Text: {response_text}")



# 定义线程池，用于控制并发数
max_concurrent_requests = 5  # 设置最大并发数为5
executor = ThreadPoolExecutor(max_concurrent_requests)


async def start_task(sciminer_request_ip, sciminer_task_id, sciminer_task_type, name):

    # 使用线程池在后台线程中执行同步代码
    loop = asyncio.get_running_loop()
    result, task_success = await loop.run_in_executor(executor, run_long_test, name)

    # 发送任务结果，更新任务状态
    await post_result(sciminer_request_ip, sciminer_task_id, sciminer_task_type, result, task_success)



# 任务的 API 接口
@app.post("/start-long-task")
async def start_long_task(
    # 固定参数
    request: Request,
    background_tasks: BackgroundTasks,
    
    # API算法需要传入的参数示例 多个工具一个openapi文件时，参数名称应当不一致
    name: str = Form(...),  # 字符串
    int_param: int = Form(...),  # 整数
    bool_param: bool = Form(...),  # 布尔值
    float_param: float = Form(...),  # 浮动
    file_param: UploadFile = File(...), # 文件，上传文件
    optional_file: Optional[UploadFile] = File(None),  # 可选, 上传文件
    optional_string: Optional[str] = Form(None),  # 可选, 字符串
    optional_int: Optional[int] = Form(None),  # 可选, 整数
    optional_bool: Optional[bool] = Form(None),  # 可选, 布尔值
    optional_float: Optional[float] = Form(None),  # 可选, 浮动值
    select_method: str = Query(description="select method", enum=["method 1", "method 2", "method 3"]) # 下拉选项
):
    try:
        sciminer_request_ip = request.headers.get("X-SCIMINER-CONSOLE-API-URL")
        sciminer_task_id = request.headers.get("X-SCIMINER-TASK-ID")
        sciminer_task_type = request.headers.get("X-SCIMINER-TASK-TYPE", None)
    
        print("sciminer_task_id:", sciminer_task_id)
        print("sciminer_request_ip:", sciminer_request_ip)
        print("sciminer_task_type:", sciminer_task_type)
        
        if name == "":
            # 抛出运行过程中的异常
            raise Exception("The current input parameter 'name' cannot be empty.")     
    
        # 将任务放入后台运行，运行完成后 返回结果并更新任务状态
        background_tasks.add_task(start_task, sciminer_request_ip, sciminer_task_id, sciminer_task_type, name)
    
        # 设置code为20000，表示当前API为非耗时API，返回的结果中"data"字段(str类型)内容即为当前API结果。
        # 设置code为20001，表示当前API为耗时API，需要通过post方式向SciMiner平台发送当前API结果，在“历史任务”中查看任务结果。
        return {"code": 20001, "message": f"Please wait a moment.", "data": ""}
    
    except Exception as e:
        # 将异常反馈到 SciMiner 平台显示
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == '__main__':

    uvicorn.run(app="your_script_name:app", host='0.0.0.0', port=6065, log_level="info")