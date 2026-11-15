import { useEffect, useRef } from "react";

const KW = /\b(public|private|protected|internal|static|readonly|sealed|abstract|async|await|return|throw|new|if|else|for|foreach|while|in|var|using|namespace|class|interface|record|enum|struct|get|set|init|this|null|true|false|try|catch|finally|override|virtual|const|void|is|not|and|or|default|nameof|typeof)\b/g;
const TY = /\b(string|int|decimal|bool|Guid|Task|DateTimeOffset|IReadOnlyList|List|Dictionary|IReadOnlyDictionary|CancellationToken|Exception)\b/g;
function hl(line) {
  const esc = line.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  const ci = esc.indexOf("//");
  const code = ci >= 0 ? esc.slice(0, ci) : esc, com = ci >= 0 ? esc.slice(ci) : "";
  const parts = code.split(/(\$?"(?:[^"\\]|\\.)*")/g);
  const out = parts.map((p, i) => (i % 2 ? `<span class="s">${p}</span>` : p.replace(KW, '<span class="k">$1</span>').replace(TY, '<span class="t">$1</span>').replace(/\[(\w+)/g, '[<span class="a">$1</span>')));
  return out.join("") + (com ? `<span class="c">${com}</span>` : "");
}
export default function CodeBlock({ W, O, file, from, to, focus, focusLine }) {
  const ref = useRef(null);
  const text = (W.w.files || {})[file];
  useEffect(() => { const el = ref.current && ref.current.querySelector("tr.focus"); if (el) el.scrollIntoView({ block: "center" }); }, [file, focusLine]);
  if (text == null) return <p className="empty">Source not available.</p>;
  const lines = text.split("\n");
  const findings = (O.review.findings || []).filter((f) => f.file === file);
  const rows = [];
  for (let i = Math.max(1, from); i <= Math.min(lines.length, to); i++) {
    const f = findings.filter((x) => x.line_start <= i && (x.line_end || x.line_start) >= i);
    const inSpan = focus && i >= focus[0] && i <= focus[1];
    const cls = [O.changedLine(file, i) ? "chg" : "", f.length ? "fnd" : "", focusLine === i ? "focus" : "", inSpan ? "span" : ""].join(" ");
    rows.push(<tr key={i} className={cls}><td className="n">{i}</td><td><span dangerouslySetInnerHTML={{ __html: hl(lines[i - 1]) }} />{f.length > 0 && f[0].line_start === i && <span className="cnote">  ◀ {f.map((x) => x.id + " " + x.title).join("; ")}</span>}</td></tr>);
  }
  return (<div ref={ref}><div className="note mono">{file}</div><div className="code"><table><tbody>{rows}</tbody></table></div></div>);
}
