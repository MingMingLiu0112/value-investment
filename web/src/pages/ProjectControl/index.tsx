import { Button, Empty, Input, Popconfirm, Select, Tabs } from "antd";
import { useMemo, useRef, useState, type ReactNode } from "react";
import { Workbench } from "../../components/Workbench";
import {
  projectConnections,
  projectControl,
  projectFlowStages,
  projectLanes,
  projectModules,
  type ProjectModule,
} from "../../data/projectControl";
import "./project-control.css";

type Lane = ProjectModule["lane"];
type ModuleId = ProjectModule["id"];
type DetailTab = "overview" | "evidence" | "task" | "notes";
type StatusFilter =
  "all" | "implementation" | "verification" | "blocked" | "verified";

type ModuleNote = {
  moduleId: string;
  direction: string;
  acceptance: string;
  updatedAt: string;
  baseCommit: string;
};
type Notes = Record<string, ModuleNote>;

const NOTES_KEY = "value-investment.project-control.notes.v1";
const NOTE_LIMIT = 6000;
const implementationLabels = {
  planned: "待实现",
  partial: "部分实现",
  implemented: "已有实现",
  connected: "已接入主链",
} as const;
const verificationLabels = {
  pending: "待验证",
  partial: "部分验证",
  verified: "已有验证",
  blocked: "验证受阻",
} as const;
const criterionLabels = {
  met: "合同有实现依据",
  partial: "部分满足",
  pending: "尚待验证",
  blocked: "当前受阻",
} as const;
const evidenceLabels = {
  source: "源码",
  test: "测试",
  ci: "CI",
  document: "文档",
} as const;
const laneLabels: Record<Lane, string> = {
  value: "价值投资",
  hotspot: "热点波段",
  shared: "共用能力",
};
const ownerReviewLabels = {
  unconfirmed: "尚未确认",
  accepted: "已接受",
  changes_requested: "要求调整",
} as const;

function ownerReviewState(module: ProjectModule) {
  const review = module.ownerReview;
  if (review.status === "unconfirmed") {
    return {
      label: ownerReviewLabels.unconfirmed,
      tone: "unconfirmed",
      summary: review.summary,
    };
  }
  const current = review.reviewedCommit === module.reviewedCommit;
  return {
    label: current
      ? ownerReviewLabels[review.status]
      : review.status === "accepted"
        ? "旧版已确认，当前待确认"
        : "旧版要求调整，当前待确认",
    tone: current ? review.status : "unconfirmed",
    summary: current
      ? `${review.summary} 记录范围：${review.reviewedScope}。`
      : `旧基线 ${review.reviewedCommit.slice(0, 8)} 的记录为“${ownerReviewLabels[review.status]}”，不自动适用于当前基线。${review.summary}`,
  };
}

function Icon({
  name,
}: {
  name: "arrow" | "copy" | "external" | "search" | "check" | "note" | "branch";
}) {
  const paths = {
    arrow: <path d="M4 10h12m-5-5 5 5-5 5" />,
    copy: (
      <>
        <rect x="7" y="7" width="10" height="11" rx="2" />
        <path d="M13 7V4a2 2 0 0 0-2-2H4a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h3" />
      </>
    ),
    external: (
      <>
        <path d="M11 3h6v6M17 3l-8 8" />
        <path d="M8 4H5a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h9a2 2 0 0 0 2-2v-3" />
      </>
    ),
    search: (
      <>
        <circle cx="8.5" cy="8.5" r="5.5" />
        <path d="m13 13 4 4" />
      </>
    ),
    check: <path d="m4 10 4 4 8-8" />,
    note: (
      <>
        <path d="M11 3H5a2 2 0 0 0-2 2v11a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-6" />
        <path d="m8 10 7-7 2 2-7 7-3 1 1-3Z" />
      </>
    ),
    branch: (
      <>
        <circle cx="5" cy="4" r="2" />
        <circle cx="5" cy="16" r="2" />
        <circle cx="15" cy="5" r="2" />
        <path d="M5 6v8m0-3h5a5 5 0 0 0 5-4" />
      </>
    ),
  };
  return (
    <svg
      className="pc-icon"
      width="20"
      height="20"
      viewBox="0 0 20 20"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {paths[name]}
    </svg>
  );
}

function readNotes(): { notes: Notes; warning: string } {
  if (typeof window === "undefined") return { notes: {}, warning: "" };
  try {
    const raw = window.localStorage.getItem(NOTES_KEY);
    if (!raw) return { notes: {}, warning: "" };
    const parsed = JSON.parse(raw);
    if (parsed?.schemaVersion !== 1 || !parsed.notes) {
      return {
        notes: {},
        warning: "已有笔记格式无法读取。原记录未覆盖，你仍可填写并复制笔记。",
      };
    }
    const notes: Notes = {};
    for (const [key, entry] of Object.entries(parsed.notes)) {
      const note = entry as Partial<ModuleNote> | null;
      if (
        note &&
        typeof note.moduleId === "string" &&
        typeof note.direction === "string" &&
        typeof note.acceptance === "string" &&
        typeof note.updatedAt === "string" &&
        typeof note.baseCommit === "string" &&
        /^[A-Za-z0-9_-]+$/.test(note.moduleId) &&
        /^[a-f0-9]{7,64}$/i.test(note.baseCommit) &&
        key === `${note.baseCommit}:${note.moduleId}`
      ) {
        notes[key] = {
          moduleId: note.moduleId,
          direction: note.direction.slice(0, NOTE_LIMIT),
          acceptance: note.acceptance.slice(0, NOTE_LIMIT),
          updatedAt: note.updatedAt,
          baseCommit: note.baseCommit,
        };
      }
    }
    return { notes, warning: "" };
  } catch {
    return {
      notes: {},
      warning: "此浏览器的本机草稿暂不可读取。你仍可填写并复制笔记。",
    };
  }
}

function noteKey(module: ProjectModule): string {
  return `${module.reviewedCommit}:${module.id}`;
}

function emptyNote(module?: ProjectModule): ModuleNote {
  return {
    moduleId: module?.id ?? "",
    direction: "",
    acceptance: "",
    updatedAt: "",
    baseCommit: module?.reviewedCommit ?? "",
  };
}

function externalHref(value: string): string | undefined {
  try {
    const url = new URL(value);
    return url.protocol === "https:" || url.protocol === "http:"
      ? url.href
      : undefined;
  } catch {
    return undefined;
  }
}

async function copyText(value: string): Promise<boolean> {
  try {
    if (typeof navigator !== "undefined" && navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(value);
      return true;
    }
  } catch {
    // Some local previews do not permit the Clipboard API; offer a local fallback.
  }
  if (typeof document === "undefined") return false;
  const activeElement = document.activeElement;
  const field = document.createElement("textarea");
  field.value = value;
  field.setAttribute("readonly", "");
  field.style.position = "fixed";
  field.style.opacity = "0";
  field.style.left = "-9999px";
  document.body.appendChild(field);
  field.select();
  let copied = false;
  try {
    copied = document.execCommand("copy");
  } catch {
    copied = false;
  } finally {
    field.remove();
    if (activeElement instanceof HTMLElement) activeElement.focus();
  }
  return copied;
}

function taskText(module: ProjectModule): string {
  const bullets = (items: readonly string[]) =>
    items.map((s) => `- ${s}`).join("\n");
  return [
    `# Codex 任务单：${module.id} · ${module.title}`,
    "",
    `项目：MingMingLiu0112/value-investment`,
    `模块核对日期：${module.reviewedAt}`,
    `模块参考源码：${module.reviewedCommit}`,
    `参考分支：${projectControl.sourceBranch}`,
    "执行前核对实际 HEAD 与未提交改动；本任务单不证明当前运行版本。",
    "",
    "## 本次目标",
    module.nextDeliverable,
    "",
    "## 当前已知状态",
    `实现：${implementationLabels[module.implementation.status]}；${module.implementation.summary}`,
    `验证：${verificationLabels[module.verification.status]}；${module.verification.summary}`,
    `用户验收：${ownerReviewState(module).label}。${ownerReviewState(module).summary}`,
    "",
    "## 允许范围",
    bullets(module.scope),
    "",
    "## 输入与输出",
    `输入：${module.inputs.join("；")}`,
    `输出：${module.outputs.join("；")}`,
    `依赖模块：${module.dependencyIds.join("、") || "无前置模块"}`,
    "",
    "## 已知限制",
    bullets(module.limitations),
    "",
    "## 禁止扩张",
    "- 只处理所选模块及完成此交付必要的依赖，复用既有服务与流程，不另建竞争实现。",
    "- 以 AGENTS.md、永久证据规则和最新用户任务界定范围；历史阶段描述不自动创建新任务。",
    "- 新增研究、规则或模型行为须版本化，不覆盖冻结历史证据，不以调整阈值制造合格机会。",
    "- 真实账户写入、生产部署、调度或收费调用依各自已有授权执行；本任务单本身不授予这些权限。",
    "- 热点新增开发保持暂停；仅当最新用户任务已明确重开时执行，不因复制此任务单而自动重开。",
    "- 不把本任务单或本机笔记当作投资批准、策略发布、真实账户授权或生产部署授权。",
    "- 不因源码存在、测试通过或页面展示而提升真实业务资格。",
    "",
    "## 验收条件",
    ...module.criteria.map(
      (criterion) =>
        `- [ ] ${criterion.id}：${criterion.text}（台账现状：${criterionLabels[criterion.status]}）`,
    ),
    "",
    "## 证据入口",
    ...module.evidence.map(
      (evidence) => `- ${evidence.label}：${evidence.url}`,
    ),
    "",
    "## 完成后必须更新进度",
    "- 更新既有 docs/current/web-first-full-product-execution-ledger.md，记录实际提交、验证命令、结果与剩余阻塞。",
    "- 同步 web/src/data/projectControl.ts 中本模块的实现、验证、交付物、验收项及本轮提交证据；未复核模块保持原版本，仅重新盘点全局后更新全局基线。",
    "- 分别报告工程实现、真实业务验证、用户验收；用户验收不得由 Codex 代为确认。",
    "- 保留 action=no_order；给出可复现的下一步，不用测试总数代替业务闭环。",
  ].join("\n");
}

function TextList({ items }: { items: readonly string[] }) {
  if (!items.length) return <p className="pc-muted">尚未登记。</p>;
  return (
    <ul className="pc-text-list">
      {items.map((item, index) => (
        <li key={`${index}-${item}`}>{item}</li>
      ))}
    </ul>
  );
}

function StatusPill({ tone, children }: { tone: string; children: ReactNode }) {
  return (
    <span className={`pc-status pc-status-${tone}`}>
      <span className="pc-status-dot" />
      {children}
    </span>
  );
}

export function ProjectControlContent() {
  const currentBatch = projectControl.batches.find(
    (batch) => batch.status === "current",
  );
  const [selectedId, setSelectedId] = useState<ModuleId>(
    currentBatch?.moduleIds[0] ?? projectModules[0].id,
  );
  const [laneFilter, setLaneFilter] = useState<Lane | "all">("all");
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const [query, setQuery] = useState("");
  const [detailTab, setDetailTab] = useState<DetailTab>("overview");
  const [initialNotes] = useState(readNotes);
  const [notes, setNotes] = useState<Notes>(initialNotes.notes);
  const [savedNotes, setSavedNotes] = useState<Notes>(initialNotes.notes);
  const [storageWarning, setStorageWarning] = useState(initialNotes.warning);
  const [feedback, setFeedback] = useState("");
  const [noteCopyFallback, setNoteCopyFallback] = useState("");
  const detailRef = useRef<HTMLElement>(null);
  const taskRef = useRef<HTMLTextAreaElement>(null);
  const directionRef = useRef<HTMLTextAreaElement>(null);

  const modulesById = useMemo(
    () => new Map(projectModules.map((module) => [module.id, module])),
    [],
  );
  const filteredModules = useMemo(() => {
    const term = query.trim().normalize("NFKC").toLowerCase();
    return projectModules.filter((module) => {
      if (laneFilter !== "all" && module.lane !== laneFilter) return false;
      if (
        statusFilter === "implementation" &&
        !["planned", "partial"].includes(module.implementation.status)
      )
        return false;
      if (
        statusFilter === "verification" &&
        !["pending", "partial"].includes(module.verification.status)
      )
        return false;
      if (
        statusFilter === "blocked" &&
        module.verification.status !== "blocked"
      )
        return false;
      if (
        statusFilter === "verified" &&
        module.verification.status !== "verified"
      )
        return false;
      const searchable = [
        module.id,
        module.title,
        module.summary,
        module.nextDeliverable,
        ...module.inputs,
        ...module.outputs,
        ...module.limitations,
      ]
        .join(" ")
        .normalize("NFKC")
        .toLowerCase();
      return !term || searchable.includes(term);
    });
  }, [laneFilter, query, statusFilter]);
  const selectedModule =
    filteredModules.find((module) => module.id === selectedId) ??
    filteredModules[0];
  const selectedTask = selectedModule ? taskText(selectedModule) : "";
  const ownerState = selectedModule
    ? ownerReviewState(selectedModule)
    : undefined;
  const note = selectedModule
    ? (notes[noteKey(selectedModule)] ?? emptyNote(selectedModule))
    : emptyNote();
  const savedNote = selectedModule
    ? savedNotes[noteKey(selectedModule)]
    : undefined;
  const olderNotes = selectedModule
    ? Object.values(savedNotes).filter(
        (entry) =>
          entry.moduleId === selectedModule.id &&
          entry.baseCommit !== selectedModule.reviewedCommit,
      )
    : [];
  const noteIsSaved = Boolean(
    savedNote &&
    savedNote.direction === note.direction &&
    savedNote.acceptance === note.acceptance,
  );

  const selectModule = (id: ModuleId, scroll = false) => {
    setSelectedId(id);
    setDetailTab("overview");
    setFeedback("");
    setNoteCopyFallback("");
    if (scroll) {
      setQuery("");
      setLaneFilter("all");
      setStatusFilter("all");
      requestAnimationFrame(() => {
        detailRef.current?.scrollIntoView({
          behavior: "smooth",
          block: "start",
        });
        detailRef.current?.focus({ preventScroll: true });
      });
    }
  };

  const copyTask = async () => {
    if (!selectedModule) return;
    const copied = await copyText(selectedTask);
    setFeedback(
      copied
        ? "任务单已复制，可粘贴给 Codex。"
        : "未能自动复制，请在任务单文本框中全选复制。",
    );
    if (!copied) {
      setDetailTab("task");
      requestAnimationFrame(() => {
        taskRef.current?.focus();
        taskRef.current?.select();
      });
    }
  };

  const updateNote = (field: "direction" | "acceptance", value: string) => {
    if (!selectedModule) return;
    setNotes((previous) => ({
      ...previous,
      [noteKey(selectedModule)]: {
        ...(previous[noteKey(selectedModule)] ?? emptyNote(selectedModule)),
        [field]: value.slice(0, NOTE_LIMIT),
      },
    }));
    setFeedback("");
    setNoteCopyFallback("");
  };

  const saveNote = () => {
    if (!selectedModule) return;
    const saved = {
      ...note,
      updatedAt: new Date().toISOString(),
      baseCommit: selectedModule.reviewedCommit,
    };
    const nextSavedNotes = {
      ...savedNotes,
      [noteKey(selectedModule)]: saved,
    };
    try {
      window.localStorage.setItem(
        NOTES_KEY,
        JSON.stringify({ schemaVersion: 1, notes: nextSavedNotes }),
      );
      setNotes((previous) => ({
        ...previous,
        [noteKey(selectedModule)]: saved,
      }));
      setSavedNotes(nextSavedNotes);
      setStorageWarning("");
      setFeedback("草稿已保存在当前浏览器。模块验收状态保持不变。");
    } catch {
      setStorageWarning("浏览器未能保存草稿；当前输入仍在页面中，请复制留存。");
      setFeedback("保存未成功，请复制笔记留存。");
    }
  };

  const clearNote = () => {
    if (!selectedModule) return;
    const nextSavedNotes = { ...savedNotes };
    delete nextSavedNotes[noteKey(selectedModule)];
    try {
      window.localStorage.setItem(
        NOTES_KEY,
        JSON.stringify({ schemaVersion: 1, notes: nextSavedNotes }),
      );
      setSavedNotes(nextSavedNotes);
      setNotes((previous) => {
        const next = { ...previous };
        delete next[noteKey(selectedModule)];
        return next;
      });
      setStorageWarning("");
      setNoteCopyFallback("");
      setFeedback("已清除当前模块、当前基线的草稿；其他模块及旧基线笔记保留。");
    } catch {
      setFeedback("未能清除本机草稿，原记录与当前输入均保留。");
    }
  };

  const copyNote = async () => {
    if (!selectedModule) return;
    const content = [
      `# 方向意见与验收笔记：${selectedModule.id} · ${selectedModule.title}`,
      `模块核对基线：${selectedModule.reviewedAt} · ${selectedModule.reviewedCommit}`,
      "性质：本机讨论草稿，不是后台批准或已完成验收。",
      "",
      "## 方向意见",
      note.direction || "（尚未填写）",
      "",
      "## 验收笔记",
      note.acceptance || "（尚未填写）",
    ].join("\n");
    const copied = await copyText(content);
    setFeedback(
      copied
        ? "笔记已复制，可带回讨论。"
        : "未能自动复制，请选中笔记文本后手动复制。",
    );
    setNoteCopyFallback(copied ? "" : content);
    if (!copied) {
      directionRef.current?.focus();
      directionRef.current?.select();
    }
  };

  const renderModuleLink = (id: ModuleId) => {
    const target = modulesById.get(id);
    if (!target) return null;
    return (
      <button
        key={id}
        className="pc-module-link"
        type="button"
        onClick={() => selectModule(id, true)}
      >
        <span>{id}</span> {target.title} <Icon name="arrow" />
      </button>
    );
  };

  const detailItems = selectedModule
    ? [
        {
          key: "overview",
          label: "模块详情",
          children: (
            <div className="pc-detail-content">
              <div className="pc-deliverable">
                <span className="pc-overline">下一项可验收交付</span>
                <p>{selectedModule.nextDeliverable}</p>
              </div>
              <section className="pc-detail-section">
                <h3>已有能力与产出</h3>
                <TextList items={selectedModule.currentOutcomes} />
              </section>
              <div className="pc-io-grid">
                <section className="pc-io-box">
                  <h3>
                    <span className="pc-small-number">IN</span>接收什么
                  </h3>
                  <TextList items={selectedModule.inputs} />
                </section>
                <section className="pc-io-box">
                  <h3>
                    <span className="pc-small-number">OUT</span>交付什么
                  </h3>
                  <TextList items={selectedModule.outputs} />
                </section>
              </div>
              <section className="pc-detail-section pc-limitations">
                <h3>当前限制与待解决事项</h3>
                <TextList items={selectedModule.limitations} />
              </section>
              <section className="pc-detail-section">
                <h3>前置依赖</h3>
                {selectedModule.dependencyIds.length ? (
                  <div className="pc-module-links">
                    {selectedModule.dependencyIds.map(renderModuleLink)}
                  </div>
                ) : (
                  <p className="pc-muted">
                    该模块没有登记前置模块，可按允许范围独立推进。
                  </p>
                )}
              </section>
              {projectConnections.some(
                (connection) => connection.from === selectedModule.id,
              ) && (
                <section className="pc-detail-section">
                  <h3>结果流向哪里</h3>
                  <div className="pc-downstream-list">
                    {projectConnections
                      .filter(
                        (connection) => connection.from === selectedModule.id,
                      )
                      .map((connection, index) => (
                        <div key={`${connection.to}-${index}`}>
                          {renderModuleLink(connection.to)}
                          <span className="pc-muted">
                            {connection.label}
                            {connection.kind === "feedback"
                              ? " · 反馈更新"
                              : ""}
                          </span>
                        </div>
                      ))}
                  </div>
                </section>
              )}
            </div>
          ),
        },
        {
          key: "evidence",
          label: `验收与证据 · ${selectedModule.evidence.length}`,
          children: (
            <div className="pc-detail-content">
              <p className="pc-section-note">
                以下检查合同覆盖情况。源码证明实现存在，测试文件不代表本版本已执行；真实业务验证与用户验收仍以上方独立状态及对应回执为准。
              </p>
              {selectedModule.ownerReview.status !== "unconfirmed" && (
                <section className="pc-review-receipt">
                  <h3>用户验收记录</h3>
                  <p>
                    {ownerReviewLabels[selectedModule.ownerReview.status]} ·{" "}
                    {selectedModule.ownerReview.reviewedAt}
                  </p>
                  <p>
                    适用源码：
                    <code>{selectedModule.ownerReview.reviewedCommit}</code>
                  </p>
                  <p>适用范围：{selectedModule.ownerReview.reviewedScope}</p>
                  {selectedModule.ownerReview.userQuote && (
                    <blockquote>
                      {selectedModule.ownerReview.userQuote}
                    </blockquote>
                  )}
                  {selectedModule.ownerReview.recordRef &&
                    (externalHref(selectedModule.ownerReview.recordRef) ? (
                      <a
                        href={externalHref(
                          selectedModule.ownerReview.recordRef,
                        )}
                        target="_blank"
                        rel="noopener noreferrer"
                      >
                        打开验收记录 <Icon name="external" />
                      </a>
                    ) : (
                      <p>记录引用：{selectedModule.ownerReview.recordRef}</p>
                    ))}
                  {selectedModule.ownerReview.reviewedCommit !==
                    selectedModule.reviewedCommit && (
                    <p>该记录属于旧基线，当前基线仍需核对。</p>
                  )}
                </section>
              )}
              <section className="pc-detail-section">
                <h3>验收条件</h3>
                <ol className="pc-criteria-list">
                  {selectedModule.criteria.map((criterion) => (
                    <li key={criterion.id}>
                      <span
                        className={`pc-criterion-mark pc-criterion-${criterion.status}`}
                      >
                        {criterion.status === "met" ? (
                          <Icon name="check" />
                        ) : criterion.status === "blocked" ? (
                          "!"
                        ) : (
                          "○"
                        )}
                      </span>
                      <div>
                        <div className="pc-criterion-heading">
                          <strong>{criterion.id}</strong>
                          <span>{criterionLabels[criterion.status]}</span>
                        </div>
                        <p>{criterion.text}</p>
                        {criterion.evidenceIds.length > 0 && (
                          <small>
                            证据编号：{criterion.evidenceIds.join(" · ")}
                          </small>
                        )}
                      </div>
                    </li>
                  ))}
                </ol>
              </section>
              <section className="pc-detail-section">
                <h3>可追溯证据</h3>
                <div className="pc-evidence-list">
                  {selectedModule.evidence.map((evidence) => {
                    const href = externalHref(evidence.url);
                    return (
                      <article key={evidence.id} className="pc-evidence-item">
                        <div>
                          <span className="pc-evidence-kind">
                            {evidenceLabels[evidence.kind]}
                          </span>
                          <code>{evidence.id}</code>
                        </div>
                        {href ? (
                          <a
                            href={href}
                            target="_blank"
                            rel="noopener noreferrer"
                          >
                            {evidence.label}
                            <Icon name="external" />
                          </a>
                        ) : (
                          <strong>{evidence.label}</strong>
                        )}
                        <p>{evidence.summary}</p>
                      </article>
                    );
                  })}
                </div>
              </section>
            </div>
          ),
        },
        {
          key: "task",
          label: "Codex 任务单",
          children: (
            <div className="pc-detail-content">
              <div className="pc-task-intro">
                <div>
                  <h3>把下一步变成明确任务</h3>
                  <p>
                    已带入本模块范围、验收条件与证据。复制后交给
                    Codex，完成时同步更新这份台账。
                  </p>
                </div>
                <Button
                  type="primary"
                  onClick={copyTask}
                  icon={<Icon name="copy" />}
                >
                  复制任务单
                </Button>
              </div>
              <label className="pc-sr-only" htmlFor="pc-task-text">
                当前模块 Codex 任务单
              </label>
              <textarea
                id="pc-task-text"
                ref={taskRef}
                className="pc-task-text"
                readOnly
                value={selectedTask}
                rows={18}
                spellCheck={false}
              />
              <p className="pc-section-note">
                复制仅生成文本。它不会启动任务、修改代码或改变任何批准状态。
              </p>
            </div>
          ),
        },
        {
          key: "notes",
          label: "方向与验收笔记",
          children: (
            <div className="pc-detail-content">
              <div className="pc-note-boundary">
                <Icon name="note" />
                <div>
                  <strong>把意见留在具体模块上</strong>
                  <p>
                    仅保存在当前浏览器，可复制回讨论。笔记不会提交到后台，也不会将模块标记为已验收；请勿填写账户、持仓或密钥。
                  </p>
                </div>
              </div>
              {storageWarning && (
                <p className="pc-storage-warning" role="alert">
                  {storageWarning}
                </p>
              )}
              <div className="pc-note-field">
                <label htmlFor="pc-direction-note">
                  方向意见 <span>希望怎样调整、优先解决什么</span>
                </label>
                <textarea
                  id="pc-direction-note"
                  ref={directionRef}
                  value={note.direction}
                  onChange={(event) =>
                    updateNote("direction", event.target.value)
                  }
                  maxLength={NOTE_LIMIT}
                  rows={5}
                  placeholder="例如：先把一家公司从证据到主估值跑通，再扩大候选覆盖。"
                />
              </div>
              <div className="pc-note-field">
                <label htmlFor="pc-acceptance-note">
                  验收笔记 <span>看过什么、还缺什么证据</span>
                </label>
                <textarea
                  id="pc-acceptance-note"
                  value={note.acceptance}
                  onChange={(event) =>
                    updateNote("acceptance", event.target.value)
                  }
                  maxLength={NOTE_LIMIT}
                  rows={5}
                  placeholder="记录实际使用结果或需要 Codex 补充的证据，不会更改正式验收状态。"
                />
              </div>
              <div className="pc-note-actions">
                <Button type="primary" onClick={saveNote}>
                  保存本机草稿
                </Button>
                <Button onClick={copyNote} icon={<Icon name="copy" />}>
                  复制笔记
                </Button>
                <Popconfirm
                  title="清除当前模块的本机草稿？"
                  description="仅清除当前源码基线下这一个模块，其他草稿保留。"
                  okText="清除此草稿"
                  cancelText="保留"
                  onConfirm={clearNote}
                >
                  <Button
                    type="text"
                    disabled={!savedNote && !note.direction && !note.acceptance}
                  >
                    清除本模块
                  </Button>
                </Popconfirm>
                <span className="pc-muted">
                  {noteIsSaved
                    ? "当前浏览器已保存"
                    : note.direction || note.acceptance
                      ? "有尚未保存的输入"
                      : "尚无本机草稿"}
                </span>
              </div>
              <p className="pc-section-note">
                草稿绑定模块 {selectedModule.id} 与源码{" "}
                {selectedModule.reviewedCommit.slice(0, 8)}，不同版本分别保存。
              </p>
              {noteCopyFallback && (
                <div className="pc-note-field">
                  <label htmlFor="pc-note-export">
                    完整笔记文本 · 可手动复制
                  </label>
                  <textarea
                    id="pc-note-export"
                    readOnly
                    value={noteCopyFallback}
                    onFocus={(event) => event.target.select()}
                    rows={8}
                  />
                </div>
              )}
              {olderNotes.length > 0 && (
                <details className="pc-older-notes">
                  <summary>
                    旧基线草稿（{olderNotes.length}）· 未合并到当前版本
                  </summary>
                  {olderNotes.map((older) => (
                    <section key={older.baseCommit}>
                      <strong>源码 {older.baseCommit.slice(0, 8)}</strong>
                      <p>{older.direction || "未填写方向意见"}</p>
                      <p>{older.acceptance || "未填写验收笔记"}</p>
                    </section>
                  ))}
                </details>
              )}
            </div>
          ),
        },
      ]
    : [];

  return (
    <div className="pc-page">
      <header className="pc-page-header">
        <div>
          <div className="pc-eyebrow">
            <Icon name="branch" />
            双策略项目工作台
          </div>
          <h1>{projectControl.title}</h1>
          <p>{projectControl.summary}</p>
        </div>
        <a className="pc-schedule-link" href="#pc-development-plan">
          查看开发顺序
          <Icon name="arrow" />
        </a>
      </header>

      <div className="pc-baseline">
        <span>
          <span className="pc-baseline-dot" />
          版本化台账
        </span>
        <span>
          核对日期 <strong>{projectControl.lastReviewed}</strong>
        </span>
        <span>
          源码基线{" "}
          <a
            href={`https://github.com/MingMingLiu0112/value-investment/commit/${projectControl.snapshotCommit}`}
            target="_blank"
            rel="noopener noreferrer"
          >
            <code>{projectControl.snapshotCommit.slice(0, 8)}</code>
            <Icon name="external" />
          </a>
        </span>
        <span className="pc-baseline-note">
          源码与验收记录，不是实时运行监控
        </span>
      </div>

      {currentBatch && (
        <section className="pc-focus-strip" aria-label="当前开发焦点">
          <div>
            <span className="pc-focus-label">当前焦点</span>
            <strong>{currentBatch.title}</strong>
            <p>{currentBatch.goal}</p>
          </div>
          <Button onClick={() => selectModule(currentBatch.moduleIds[0], true)}>
            查看当前模块
            <Icon name="arrow" />
          </Button>
        </section>
      )}

      <section
        className="pc-architecture pc-panel"
        aria-labelledby="pc-architecture-title"
      >
        <div className="pc-section-heading">
          <div>
            <span className="pc-overline">01 / 业务架构</span>
            <h2 id="pc-architecture-title">两条策略独立研究，共用账户风险</h2>
          </div>
          <span className="pc-section-hint">
            点击任一节点，查看模块与下一项交付
          </span>
        </div>
        <div className="pc-lanes">
          {projectLanes
            .filter((lane) => lane.id !== "shared")
            .map((lane) => (
              <section
                key={lane.id}
                className={`pc-lane pc-lane-${lane.id}`}
                aria-label={lane.title}
              >
                <div className="pc-lane-heading">
                  <div>
                    <span className="pc-lane-marker" />
                    <h3>{lane.title}</h3>
                  </div>
                  <span className="pc-lane-policy">
                    {lane.developmentStatus === "paused"
                      ? "开发暂缓 · 保留独立路径"
                      : "当前推进"}
                  </span>
                  <p>{lane.subtitle}</p>
                </div>
                <div className={`pc-flow pc-flow-${lane.id}`}>
                  {projectFlowStages
                    .filter((stage) => stage.lane === lane.id)
                    .map((stage, index) => (
                      <button
                        key={stage.id}
                        type="button"
                        className={`pc-flow-stage ${selectedModule && stage.moduleIds.includes(selectedModule.id) ? "is-selected" : ""}`}
                        onClick={() => selectModule(stage.moduleIds[0], true)}
                        aria-label={`${lane.title}：${stage.title}，查看模块 ${stage.moduleIds.join("、")}`}
                      >
                        <span className="pc-stage-top">
                          <span className="pc-stage-number">
                            {String(index + 1).padStart(2, "0")}
                          </span>
                          <Icon name="arrow" />
                        </span>
                        <strong>{stage.title}</strong>
                        <span className="pc-stage-caption">
                          {stage.caption}
                        </span>
                        <span className="pc-stage-ids">
                          {stage.moduleIds.join(" · ")}
                        </span>
                      </button>
                    ))}
                </div>
              </section>
            ))}
        </div>
        <div className="pc-convergence">
          <span />
          <p>
            证券级结论汇入共用层 <span>· 热点准入不依赖价值 G3</span>
          </p>
          <span />
        </div>
        <div className="pc-shared-flow">
          {projectFlowStages
            .filter((stage) => stage.lane === "shared")
            .map((stage) => (
              <button
                key={stage.id}
                type="button"
                className={`pc-shared-stage ${selectedModule && stage.moduleIds.includes(selectedModule.id) ? "is-selected" : ""}`}
                onClick={() => selectModule(stage.moduleIds[0], true)}
              >
                <span className="pc-stage-ids">
                  {stage.moduleIds.join(" · ")}
                </span>
                <strong>{stage.title}</strong>
                <span>{stage.caption}</span>
                <Icon name="arrow" />
              </button>
            ))}
        </div>
        <p className="pc-map-note">
          流程图按业务分组；实际依赖以模块详情为准。买卖在券商端由你操作，成交登记后再更新持仓与风险。
        </p>
      </section>

      <section
        className="pc-module-workspace"
        ref={detailRef}
        tabIndex={-1}
        aria-labelledby="pc-modules-title"
      >
        <div className="pc-section-heading">
          <div>
            <span className="pc-overline">02 / 模块与验收</span>
            <h2 id="pc-modules-title">做到哪一步，有什么证据</h2>
          </div>
          <p className="pc-section-hint">实现、验证、用户验收分别记录</p>
        </div>
        <div className="pc-filter-bar">
          <div className="pc-lane-filters" role="group" aria-label="按策略筛选">
            {(["all", "value", "hotspot", "shared"] as const).map((lane) => (
              <button
                key={lane}
                type="button"
                aria-pressed={laneFilter === lane}
                className={laneFilter === lane ? "is-active" : ""}
                onClick={() => {
                  setLaneFilter(lane);
                  setFeedback("");
                  setNoteCopyFallback("");
                }}
              >
                {lane === "all" ? "全部模块" : laneLabels[lane]}
              </button>
            ))}
          </div>
          <div className="pc-search-filters">
            <Input
              allowClear
              prefix={<Icon name="search" />}
              aria-label="搜索模块"
              placeholder="搜索模块、能力或阻塞"
              value={query}
              onChange={(event) => {
                setQuery(event.target.value);
                setFeedback("");
                setNoteCopyFallback("");
              }}
            />
            <Select
              aria-label="按状态筛选"
              value={statusFilter}
              onChange={(value) => {
                setStatusFilter(value);
                setFeedback("");
                setNoteCopyFallback("");
              }}
              options={[
                { value: "all", label: "全部状态" },
                { value: "implementation", label: "实现待补" },
                { value: "verification", label: "验证待补" },
                { value: "blocked", label: "验证受阻" },
                { value: "verified", label: "已有验证" },
              ]}
            />
          </div>
        </div>

        {selectedModule ? (
          <div className="pc-module-grid">
            <aside
              className="pc-module-directory pc-panel"
              aria-label="模块目录"
            >
              <div className="pc-directory-heading">
                <strong>模块目录</strong>
                <span>
                  {filteredModules.length} / {projectModules.length}
                </span>
              </div>
              <div className="pc-directory-list">
                {filteredModules.map((module) => (
                  <button
                    type="button"
                    key={module.id}
                    aria-pressed={module.id === selectedModule.id}
                    onClick={() => selectModule(module.id)}
                    className={`pc-directory-item ${module.id === selectedModule.id ? "is-selected" : ""}`}
                  >
                    <div className="pc-directory-title">
                      <span className={`pc-id pc-id-${module.lane}`}>
                        {module.id}
                      </span>
                      <strong>{module.title}</strong>
                      <Icon name="arrow" />
                    </div>
                    <div className="pc-directory-status">
                      <span>
                        {implementationLabels[module.implementation.status]}
                      </span>
                      <span
                        className={`pc-directory-verification is-${module.verification.status}`}
                      >
                        {verificationLabels[module.verification.status]}
                      </span>
                    </div>
                  </button>
                ))}
              </div>
            </aside>
            <article
              className="pc-module-detail pc-panel"
              aria-label={`${selectedModule.id} ${selectedModule.title} 模块详情`}
            >
              <div className="pc-detail-header">
                <div>
                  <div className="pc-detail-kicker">
                    <span className={`pc-id pc-id-${selectedModule.lane}`}>
                      {selectedModule.id}
                    </span>
                    <span>{laneLabels[selectedModule.lane]}</span>
                  </div>
                  <h2>{selectedModule.title}</h2>
                  <p>{selectedModule.summary}</p>
                  <div className="pc-module-version">
                    <span>模块核对 {selectedModule.reviewedAt}</span>
                    <a
                      href={`https://github.com/MingMingLiu0112/value-investment/commit/${selectedModule.reviewedCommit}`}
                      target="_blank"
                      rel="noopener noreferrer"
                    >
                      <code>{selectedModule.reviewedCommit.slice(0, 8)}</code>
                      <Icon name="external" />
                    </a>
                  </div>
                </div>
                <Button
                  onClick={() => setDetailTab("task")}
                  icon={<Icon name="copy" />}
                >
                  生成任务单
                </Button>
              </div>
              <div className="pc-status-grid">
                <div>
                  <span className="pc-status-label">工程实现</span>
                  <StatusPill tone={selectedModule.implementation.status}>
                    {implementationLabels[selectedModule.implementation.status]}
                  </StatusPill>
                  <p>{selectedModule.implementation.summary}</p>
                </div>
                <div>
                  <span className="pc-status-label">业务验证</span>
                  <StatusPill tone={selectedModule.verification.status}>
                    {verificationLabels[selectedModule.verification.status]}
                  </StatusPill>
                  <p>{selectedModule.verification.summary}</p>
                </div>
                <div>
                  <span className="pc-status-label">用户验收</span>
                  <StatusPill tone={ownerState?.tone ?? "unconfirmed"}>
                    {ownerState?.label}
                  </StatusPill>
                  <p>{ownerState?.summary}</p>
                </div>
              </div>
              <Tabs
                activeKey={detailTab}
                onChange={(key) => {
                  setDetailTab(key as DetailTab);
                  setFeedback("");
                }}
                items={detailItems}
                className="pc-detail-tabs"
              />
              <div
                className={`pc-feedback ${feedback ? "is-visible" : ""}`}
                role="status"
                aria-live="polite"
              >
                {feedback}
              </div>
            </article>
          </div>
        ) : (
          <div className="pc-empty pc-panel">
            <Empty description="没有符合当前条件的模块" />
            <p>试试其他关键词，或清除策略和状态筛选。</p>
            <Button
              onClick={() => {
                setQuery("");
                setLaneFilter("all");
                setStatusFilter("all");
              }}
            >
              清除筛选
            </Button>
          </div>
        )}
      </section>

      <section
        id="pc-development-plan"
        className="pc-development-plan"
        aria-labelledby="pc-plan-title"
      >
        <div className="pc-section-heading">
          <div>
            <span className="pc-overline">03 / 开发顺序</span>
            <h2 id="pc-plan-title">按可验收交付，逐步推进</h2>
          </div>
          <p className="pc-section-hint">
            以退出条件推进，不代表自动排期或执行授权
          </p>
        </div>
        <div className="pc-batch-grid">
          {projectControl.batches.map((batch, index) => (
            <article
              key={batch.id}
              className={`pc-batch pc-panel pc-batch-${batch.status}`}
            >
              <div className="pc-batch-top">
                <span className="pc-batch-number">
                  {String(index + 1).padStart(2, "0")}
                </span>
                <span>
                  {batch.status === "current"
                    ? "当前批次"
                    : batch.status === "next"
                      ? "下一批次"
                      : "后续批次"}
                </span>
              </div>
              <h3>{batch.title}</h3>
              <p>{batch.goal}</p>
              <h4>交付物</h4>
              <TextList items={batch.deliverables} />
              <h4>进入下一步的条件</h4>
              <TextList items={batch.exitCriteria} />
              <div className="pc-batch-modules">
                {batch.moduleIds.map((id) => (
                  <button
                    type="button"
                    key={id}
                    onClick={() => selectModule(id, true)}
                    aria-label={`查看 ${id} ${modulesById.get(id)?.title ?? "模块"}`}
                  >
                    {id}
                    <Icon name="arrow" />
                  </button>
                ))}
              </div>
            </article>
          ))}
        </div>
      </section>

      <footer className="pc-page-footer">
        <div>
          <Icon name="branch" />
          <strong>一份台账，三种状态</strong>
        </div>
        <p>{projectControl.scopeNote}</p>
        <details>
          <summary>查看本页的边界与更新约定</summary>
          <TextList items={projectControl.boundaries} />
          <p>
            模块状态由版本化项目资料维护。本机笔记不改变状态；每次交付需要同步实际提交、证据与验收条件。
          </p>
          <p className="pc-source-branch">
            参考分支：<code>{projectControl.sourceBranch}</code>
          </p>
        </details>
      </footer>
    </div>
  );
}

export default function ProjectControl() {
  return (
    <Workbench>
      <ProjectControlContent />
    </Workbench>
  );
}
