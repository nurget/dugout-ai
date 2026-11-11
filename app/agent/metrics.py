from dataclasses import dataclass, field
from time import perf_counter
from uuid import uuid4

@dataclass
class ToolMetric:
    name: str
    duration_ms: float
    success: bool
    
@dataclass
class AgentMetrics:
    run_id: str = field(default_factory=lambda: str(uuid4()))
    started_at: float = field(default_factory=perf_counter)
    versions: dict[str, str] = field(default_factory=dict)
    
    llm_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    
    # 모델이 사용량을 반환하지 않은 요청을 0 토큰으로 취급하지 말 것.
    usage_missing: bool = False
    
    tools: list[ToolMetric] = field(default_factory=list)
    llm_call_metrics: list[dict] = field(default_factory=list)
    
    def record_llm_call(
        self,
        input_tokens: int | None,
        output_tokens: int | None,
        *,
        stage: str = "UNKNOWN",
        duration_ms: float | None = None,
        cached_input_tokens: int | None = None,
    ) -> None:
        self.llm_calls += 1
        self.llm_call_metrics.append({
            "sequence": self.llm_calls,
            "stage": stage,
            "duration_ms": round(duration_ms, 2) if duration_ms is not None else None,
            "input_tokens": input_tokens,
            "cached_input_tokens": cached_input_tokens,
            "output_tokens": output_tokens,
        })
        
        if input_tokens is None or output_tokens is None:
            self.usage_missing = True
            return
        
        self.input_tokens += input_tokens
        self.output_tokens += output_tokens
        
    def record_tool(
        self,
        name: str,
        duration_ms: float,
        success: bool,
    ) -> None:
        self.tools.append(
            ToolMetric(
                name=name,
                duration_ms=round(duration_ms, 2),
                success=success,
            )
        )
    
    def snapshot(self) -> dict:
        return {
            "run_id": self.run_id,
            "duration_ms": round(
                (perf_counter() - self.started_at) * 1000,
                2,
            ),
            "llm_calls": self.llm_calls,
            **self.versions,
            "llm_call_metrics": self.llm_call_metrics,
            "input_tokens": (
                None if self.usage_missing else self.input_tokens
            ),
            "output_tokens": (
                None if self.usage_missing else self.output_tokens
            ),
            "tool_count": len(self.tools),
            "tools": [
                {
                    "name": tool.name,
                    "duration_ms": tool.duration_ms,
                    "success": tool.success,
                }
                for tool in self.tools
            ],
        }
