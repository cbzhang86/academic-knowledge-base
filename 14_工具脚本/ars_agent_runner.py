#!/usr/bin/env python3
"""
ARS 多 Agent 替代方案 — 直接调用 DeepSeek API

问题: Claude Code 2.1.166+ 的 Agent 工具存在 thinking + reasoning_effort
参数冲突，导致 ARS 子 Agent 无法使用。

方案: 绕过 Agent 框架，直接用 HTTP 调 DeepSeek Anthropic 兼容 API，
将 ARS 的 Agent prompt 作为系统提示注入，通过多轮对话实现多 Agent 协作。

用法:
  python ars_agent_runner.py plan          # 论文规划阶段
  python ars_agent_runner.py write         # 论文写作阶段
  python ars_agent_runner.py review        # 审稿阶段
  python ars_agent_runner.py full          # 全流程

环境变量:
  ANTHROPIC_BASE_URL  — DeepSeek/cc-switch 地址（默认 http://127.0.0.1:15721）
  ANTHROPIC_API_KEY   — API key（默认自动从 settings.json 读取）
"""

import sys, os, json, time
sys.stdout.reconfigure(encoding='utf-8')
from pathlib import Path

# ============ 配置 ============

API_KEY = os.environ.get(
    "ANTHROPIC_AUTH_TOKEN",
    "sk-d12c57bcadf441ce9d34df78160e1031"
)

BASE_URL = os.environ.get(
    "ANTHROPIC_BASE_URL",
    "http://127.0.0.1:15721"
)

MODEL_HAIKU = "claude-haiku-4-5"    # → deepseek-v4-flash
MODEL_SONNET = "claude-sonnet-4-6"  # → deepseek-v4-pro

DEFAULT_MAX_TOKENS = 8192

# ============ Agent Prompt 模板 ============

AGENTS = {
    "research_architect": {
        "name": "Research Architect — 方法论蓝图设计",
        "model": MODEL_HAIKU,
        "max_tokens": 4096,
        "system_prompt": "你是研究架构师。请根据研究主题，输出研究方法论蓝图。"
    },

    "synthesis_agent": {
        "name": "Synthesis Agent — 跨篇综合与知识整合",
        "model": MODEL_SONNET,
        "max_tokens": 8192,
        "system_prompt": "你是综合分析Agent。请整合文献材料，输出跨篇综合分析。"
    },

    "report_compiler": {
        "name": "Report Compiler — 论文报告生成",
        "model": MODEL_SONNET,
        "max_tokens": 16384,
        "system_prompt": "你是论文报告Agent。请输出规范学术论文。"
    },

    "reviewer": {
        "name": "审稿 Agent — 7维质量评估",
        "model": MODEL_HAIKU,
        "max_tokens": 4096,
        "system_prompt": "你是学术审稿人。请从7个维度对论文评分。"
    }
}

# ============ API 调用 ============

class DeepSeekClient:
    """DeepSeek Anthropic 兼容 API 客户端"""

    def __init__(self, base_url: str = None, api_key: str = None):
        self.base_url = (base_url or BASE_URL).rstrip("/")
        self.api_key = api_key or API_KEY

    def call(self, model: str, system: str, messages: list,
             max_tokens: int = 4096, temperature: float = 0.7) -> str:
        """调用 API，自动处理 thinking + reasoning_effort 兼容"""
        from urllib.request import Request, urlopen, HTTPError
        import ssl

        payload = {
            "model": model,
            "max_tokens": max_tokens,
            "system": system,
            "thinking": {"type": "enabled", "budget_tokens": min(max_tokens // 2, 4096)},
            "messages": messages,
            "temperature": temperature,
        }

        body = json.dumps(payload).encode("utf-8")

        req = Request(
            f"{self.base_url}/v1/messages",
            data=body,
            headers={
                "Content-Type": "application/json",
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
            },
            method="POST"
        )

        try:
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE

            resp = urlopen(req, context=ctx, timeout=120)
            result = json.loads(resp.read())

            # 提取文本内容（跳过 thinking block）
            text_parts = []
            for block in result.get("content", []):
                if block.get("type") == "text" and block.get("text"):
                    text_parts.append(block["text"])

            return "\n".join(text_parts)

        except HTTPError as e:
            err_body = e.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"API {e.code}: {err_body[:500]}")

    def stream_call(self, model: str, system: str, messages: list,
                    max_tokens: int = 4096):
        """流式调用，实时输出"""
        from urllib.request import Request, urlopen, HTTPError
        import ssl

        payload = {
            "model": model,
            "max_tokens": max_tokens,
            "system": system,
            "thinking": {"type": "enabled", "budget_tokens": min(max_tokens // 2, 4096)},
            "messages": messages,
            "stream": True,
            "temperature": 0.7,
        }

        body = json.dumps(payload).encode("utf-8")

        req = Request(
            f"{self.base_url}/v1/messages",
            data=body,
            headers={
                "Content-Type": "application/json",
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
            },
            method="POST"
        )

        try:
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE

            resp = urlopen(req, context=ctx, timeout=300)
            buffer = ""

            for chunk in resp:
                line = chunk.decode("utf-8", errors="replace").strip()
                if not line:
                    continue
                if line.startswith("data: "):
                    data_str = line[6:]
                    if data_str == "[DONE]":
                        break
                    try:
                        data = json.loads(data_str)
                        etype = data.get("type")
                        # streaming content_block_start
                        if etype == "content_block_start":
                            block = data.get("content_block", {})
                            if block.get("type") == "text" and block.get("text"):
                                print(block["text"], end="", flush=True)
                                buffer += block["text"]
                        # streaming content_block_delta
                        if etype == "content_block_delta":
                            delta = data.get("delta", {})
                            if delta.get("type") == "text_delta":
                                text = delta.get("text", "")
                                if text:
                                    print(text, end="", flush=True)
                                    buffer += text
                    except json.JSONDecodeError:
                        continue
            print()
            return buffer

        except HTTPError as e:
            err_body = e.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"API {e.code}: {err_body[:500]}")


# ============ 多 Agent 编排 ============

class ARSAgentPipeline:
    """替代 ARS 多 Agent 协作的直调方案"""

    def __init__(self, client: DeepSeekClient = None):
        self.client = client or DeepSeekClient()
        self.history = []

    def run_agent(self, agent_name: str, user_input: str,
                  stream: bool = True) -> str:
        """运行单个 Agent"""
        agent = AGENTS[agent_name]

        messages = [{"role": "user", "content": user_input}]
        if self.history:
            messages = self.history + messages

        print(f"\n{'='*60}")
        print(f"  ▶ Agent: {agent['name']}")
        print(f"  ▶ 模型: {agent['model']}")
        print(f"{'='*60}\n")

        start = time.time()

        if stream:
            result = self.client.stream_call(
                model=agent["model"],
                system=agent["system_prompt"],
                messages=messages,
                max_tokens=agent["max_tokens"],
            )
        else:
            result = self.client.call(
                model=agent["model"],
                system=agent["system_prompt"],
                messages=messages,
                max_tokens=agent["max_tokens"],
            )
            print(result[:500] + "..." if len(result) > 500 else result)
            print()

        elapsed = time.time() - start
        print(f"\n[完成] {elapsed:.0f}秒, {len(result)}字符")

        # 存入历史
        self.history.append({"role": "user", "content": user_input})
        self.history.append({"role": "assistant", "content": result})

        return result

    def plan(self, topic: str):
        """论文规划阶段 — 研究架构师"""
        prompt = f"""请为以下研究主题设计方法论蓝图：

研究主题: {topic}

请输出：
1. 推荐的研究范式
2. 具体研究方法
3. 数据策略
4. 分析框架
5. 效度标准"""
        return self.run_agent("research_architect", prompt, stream=True)

    def write(self, topic: str, literature: str):
        """论文写作阶段 — 综合+汇编两 Agent 协作"""
        # Step 1: 综合 Agent
        synthesis_prompt = f"""请整合以下研究主题和文献材料，进行跨篇综合分析：

研究主题: {topic}

文献材料:
{literature[:8000]}

请输出：
1. 核心主题提取
2. 发现聚合（按主题聚类）
3. 证据冲突识别
4. 研究空白映射"""
        synthesis_result = self.run_agent("synthesis_agent", synthesis_prompt, stream=True)

        # Step 2: 报告汇编 Agent
        compile_prompt = f"""请基于以下研究主题和文献综合分析结果，撰写完整学术论文：

研究主题: {topic}

文献综合分析结果:
{synthesis_result[:12000]}

请输出CSSCI标准格式的完整论文。"""
        return self.run_agent("report_compiler", compile_prompt, stream=True)

    def review(self, paper: str):
        """审稿阶段"""
        prompt = f"""请审阅以下论文初稿：

{paper[:8000]}

按7个维度评分，每维必须有评价性理由。"""
        return self.run_agent("reviewer", prompt, stream=True)

    def full(self, topic: str, literature: str = ""):
        """全流程"""
        print("\n" + "="*60)
        print("  ARS 全流程 - 阶段 1/3: 方法论设计")
        print("="*60)
        self.plan(topic)

        print("\n" + "="*60)
        print("  ARS 全流程 - 阶段 2/3: 论文写作")
        print("="*60)
        paper = self.write(topic, literature)

        print("\n" + "="*60)
        print("  ARS 全流程 - 阶段 3/3: 审稿")
        print("="*60)
        self.review(paper)


# ============ CLI 入口 ============

def main():
    import argparse

    parser = argparse.ArgumentParser(description="ARS Agent Runner — 直接调用 DeepSeek API")
    sub = parser.add_subparsers(dest="cmd")

    p_plan = sub.add_parser("plan", help="论文规划")
    p_plan.add_argument("topic", help="研究主题")

    p_write = sub.add_parser("write", help="论文写作")
    p_write.add_argument("topic", help="研究主题")
    p_write.add_argument("--literature", "-l", help="文献材料文件路径")

    p_review = sub.add_parser("review", help="审稿")
    p_review.add_argument("file", help="论文文件路径")

    p_full = sub.add_parser("full", help="全流程")
    p_full.add_argument("topic", help="研究主题")
    p_full.add_argument("--literature", "-l", help="文献材料文件路径")

    args = parser.parse_args()

    client = DeepSeekClient()
    pipeline = ARSAgentPipeline(client)

    if args.cmd == "plan":
        pipeline.plan(args.topic)

    elif args.cmd == "write":
        lit = ""
        if args.literature:
            lit_path = Path(args.literature)
            if lit_path.exists():
                lit = lit_path.read_text(encoding="utf-8", errors="replace")
            else:
                print(f"[ERROR] 文献文件不存在: {args.literature}")
                return 1
        pipeline.write(args.topic, lit)

    elif args.cmd == "review":
        paper_path = Path(args.file)
        if not paper_path.exists():
            print(f"[ERROR] 文件不存在: {args.file}")
            return 1
        paper = paper_path.read_text(encoding="utf-8", errors="replace")
        pipeline.review(paper)

    elif args.cmd == "full":
        lit = ""
        if args.literature:
            lit_path = Path(args.literature)
            if lit_path.exists():
                lit = lit_path.read_text(encoding="utf-8", errors="replace")
        pipeline.full(args.topic, lit)

    else:
        parser.print_help()

    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
