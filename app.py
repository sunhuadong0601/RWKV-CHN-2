import gradio as gr
import os, gc, torch
from datetime import datetime
from huggingface_hub import hf_hub_download
from pynvml import *
nvmlInit()
gpu_h = nvmlDeviceGetHandleByIndex(0)
ctx_limit = 2048
desc = f'''链接：<a href='https://github.com/BlinkDL/ChatRWKV' target="_blank" style="margin:0 0.5em">ChatRWKV</a><a href='https://github.com/BlinkDL/RWKV-LM' target="_blank" style="margin:0 0.5em">RWKV-LM</a><a href="https://pypi.org/project/rwkv/" target="_blank" style="margin:0 0.5em">RWKV pip package</a><a href="https://zhuanlan.zhihu.com/p/618011122" target="_blank" style="margin:0 0.5em">知乎教程</a>
'''

os.environ["RWKV_JIT_ON"] = '1'
os.environ["RWKV_CUDA_ON"] = '1' # if '1' then use CUDA kernel for seq mode (much faster)

from rwkv.model import RWKV
# model_path = hf_hub_download(repo_id="BlinkDL/rwkv-4-novel", filename="RWKV-4-Novel-7B-v1-Chn-20230409-ctx4096.pth")
# model = RWKV(model=model_path, strategy='cuda fp16i8 *12 -> cuda fp16')
model = RWKV(model='/workspace/RWKV-4-Novel-7B-v1-Chn-20230409-ctx4096', strategy='cuda fp16i8 *12 -> cuda fp16')
from rwkv.utils import PIPELINE, PIPELINE_ARGS
pipeline = PIPELINE(model, "20B_tokenizer.json")

def infer(
        ctx,
        token_count=10,
        temperature=1.0,
        top_p=0.8,
        presencePenalty = 0.1,
        countPenalty = 0.1,
):
    args = PIPELINE_ARGS(temperature = max(0.2, float(temperature)), top_p = float(top_p),
                     alpha_frequency = countPenalty,
                     alpha_presence = presencePenalty,
                     token_ban = [0], # ban the generation of some tokens
                     token_stop = []) # stop generation whenever you see any token here

    ctx = ctx.strip().split('\n')
    for c in range(len(ctx)):
        ctx[c] = ctx[c].strip().strip('\u3000').strip('\r')
    ctx = list(filter(lambda c: c != '', ctx))
    ctx = '\n' + ('\n'.join(ctx)).strip()
    if ctx == '':
        ctx = '\n'

    # gpu_info = nvmlDeviceGetMemoryInfo(gpu_h)
    # print(f'vram {gpu_info.total} used {gpu_info.used} free {gpu_info.free}',flush=True)
    
    all_tokens = []
    out_last = 0
    out_str = ''
    occurrence = {}
    state = None
    for i in range(int(token_count)):
        out, state = model.forward(pipeline.encode(ctx)[-ctx_limit:] if i == 0 else [token], state)
        for n in args.token_ban:
            out[n] = -float('inf')
        for n in occurrence:
            out[n] -= (args.alpha_presence + occurrence[n] * args.alpha_frequency)

        token = pipeline.sample_logits(out, temperature=args.temperature, top_p=args.top_p)
        if token in args.token_stop:
            break
        all_tokens += [token]
        if token not in occurrence:
            occurrence[token] = 1
        else:
            occurrence[token] += 1
        
        tmp = pipeline.decode(all_tokens[out_last:])
        if '\ufffd' not in tmp:
            out_str += tmp
            yield out_str
            out_last = i + 1
    gc.collect()
    torch.cuda.empty_cache()
    yield out_str

examples = [
    ["通过基因改造，修真", 200, 1.3, 0.7, 0.1, 0.1],
    ["我问智脑：“三体人发来了信息，告诉我不要回答，这是他们的阴谋吗？”", 200, 1.3, 0.7, 0.1, 0.1],
    ["“三体人的修仙功法与地球不同，最大的区别", 200, 1.3, 0.7, 0.1, 0.1],
    ["“我们都知道，魔法的运用有四个阶段，第一", 200, 1.3, 0.7, 0.1, 0.1],
    ["无论怎样，我必须将这些恐龙养大", 200, 1.3, 0.7, 0.1, 0.1],
    ["“区区", 200, 1.3, 0.7, 0.1, 0.1],
]

iface = gr.Interface(
    fn=infer,
    description=f'''这是纯网文模型，去除了英文和代码能力，但写小白文更强。<b>请点击例子（在页面底部）</b>，可编辑内容。这里只看输入的最后约1200字，请写好，标点规范，无错别字，否则电脑会模仿你的错误。<b>为避免占用资源，每次生成限制长度。可将输出内容复制到输入，然后继续生成</b>。推荐提高temp改善文采，降低topp改善逻辑，提高两个penalty避免重复，具体幅度请自己实验。{desc}''',
    allow_flagging="never",
    inputs=[
        gr.Textbox(lines=10, label="Prompt 输入的前文", value="通过基因改造，修真"),  # prompt
        gr.Slider(10, 200, step=10, value=200, label="token_count 每次生成的长度"),  # token_count
        gr.Slider(0.2, 2.0, step=0.1, value=1.3, label="temperature 默认1.3，高则变化丰富，低则保守求稳"),  # temperature
        gr.Slider(0.0, 1.0, step=0.05, value=0.7, label="top_p 默认0.7，高则标新立异，低则循规蹈矩"),  # top_p
        gr.Slider(0.0, 1.0, step=0.1, value=0.1, label="presencePenalty 默认0.1，避免写过的类似字"),  # presencePenalty
        gr.Slider(0.0, 1.0, step=0.1, value=0.1, label="countPenalty 默认0.1，额外避免写过多次的类似字"),  # countPenalty
    ],
    outputs=gr.Textbox(label="Output 输出的续写", lines=28),
    examples=examples,
    cache_examples=False,
).queue()

demo = gr.TabbedInterface(
    [iface], ["Generative"]
)

demo.queue(max_size=5)
demo.launch(share=False)
