"""Run the five specialist reviewers in parallel (one Gemini call each)."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List, Tuple

from .models import Dimension, Finding, Refusal, SpecialistOutput
from .prompts import specialist_prompt, specialist_system

PREFIX = {Dimension.CORRECTNESS: "C", Dimension.ARCHITECTURE: "A", Dimension.SAFETY: "S",
          Dimension.TESTS: "T", Dimension.MAINTAINABILITY: "M", Dimension.PERFORMANCE: "P"}


def run_specialists(client, model: str, dims: List[Dimension], prompt_inputs: Dict,
                    max_workers: int = 6, optimization: bool = False) -> Tuple[Dict[Dimension, SpecialistOutput], List[Finding],
                                                   List[Refusal], List[str]]:
    outputs: Dict[Dimension, SpecialistOutput] = {}
    errors: List[str] = []
    prompt = specialist_prompt(**prompt_inputs)

    def one(dim: Dimension):
        return dim, client.generate(role=f"specialist:{dim.value}", model=model,
                                    system=specialist_system(dim, optimization), prompt=prompt, schema=SpecialistOutput)

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = [pool.submit(one, d) for d in dims]
        for fut in futures:
            try:
                dim, out = fut.result()
                outputs[dim] = out
            except Exception as e:
                errors.append(str(e))

    findings: List[Finding] = []
    refusals: List[Refusal] = []
    for dim in dims:
        out = outputs.get(dim)
        if out is None:
            refusals.append(Refusal(source=f"specialist:{dim.value}", topic=f"{dim.value} review",
                                    reason="The specialist call failed, so this dimension was NOT reviewed."))
            continue
        for i, lf in enumerate(out.findings, start=1):
            findings.append(Finding(id=f"{PREFIX[dim]}{i:02d}", dimension=dim, source=f"specialist:{dim.value}",
                                    **lf.model_dump()))
        for r in out.refusals:
            refusals.append(Refusal(source=f"specialist:{dim.value}", topic=r.topic, reason=r.reason))
    return outputs, findings, refusals, errors
