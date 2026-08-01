import {
  useEffect,
  useId,
  useRef,
  type ButtonHTMLAttributes,
  type PropsWithChildren,
  type ReactNode
} from "react";
import { AlertTriangle, Inbox, LoaderCircle, X } from "lucide-react";

export function Button({
  variant = "primary",
  size = "medium",
  loading = false,
  type = "button",
  children,
  className = "",
  disabled,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary" | "quiet" | "danger";
  size?: "small" | "medium";
  loading?: boolean;
}) {
  return (
    <button
      type={type}
      className={`button button--${variant} button--${size} ${className}`}
      disabled={disabled || loading}
      {...props}
    >
      {loading && <LoaderCircle className="spin" size={15} />}
      {children}
    </button>
  );
}

export function StatusBadge({
  status,
  children
}: PropsWithChildren<{ status: string }>) {
  const labels: Record<string, string> = {
    queued: "排队中",
    running: "运行中",
    waiting_for_screening: "待人工筛选",
    completed: "已完成",
    failed: "失败",
    cancelled: "已取消",
    pending: "待处理",
    included: "已纳入",
    excluded: "已排除",
    maybe: "待讨论",
    conflict: "有分歧"
  };
  const label =
    typeof children === "string" && children === status
      ? (labels[status] ?? children)
      : (children ?? labels[status] ?? status);
  return (
    <span className={`status-badge status-badge--${status.replaceAll("_", "-")}`}>
      <i />
      {label}
    </span>
  );
}

export function reviewTypeLabel(value: string) {
  return (
    {
      narrative: "叙述性综述",
      scoping: "范围综述",
      systematic: "系统综述",
      thesis: "论文调研"
    } as Record<string, string>
  )[value] ?? value;
}

export function SectionTitle({
  eyebrow,
  title,
  detail,
  action
}: {
  eyebrow?: string;
  title: string;
  detail?: string;
  action?: ReactNode;
}) {
  return (
    <header className="section-title">
      <div>
        {eyebrow && <span className="section-title__context">{eyebrow}</span>}
        <h2>{title}</h2>
        {detail && <p>{detail}</p>}
      </div>
      {action && <div className="section-title__action">{action}</div>}
    </header>
  );
}

export function EmptyState({
  title,
  detail,
  action,
  icon = <Inbox size={24} />
}: {
  title: string;
  detail: string;
  action?: ReactNode;
  icon?: ReactNode;
}) {
  return (
    <div className="empty-state">
      <div className="empty-state__icon">{icon}</div>
      <h3>{title}</h3>
      <p>{detail}</p>
      {action}
    </div>
  );
}

export function ErrorState({
  error,
  retry
}: {
  error: unknown;
  retry?: () => void;
}) {
  const message = error instanceof Error ? error.message : "发生未知错误";
  return (
    <div className="notice notice--error">
      <AlertTriangle size={18} />
      <div>
        <strong>数据没有加载成功</strong>
        <p>{message}</p>
      </div>
      {retry && (
        <Button variant="quiet" size="small" onClick={retry}>
          重试
        </Button>
      )}
    </div>
  );
}

export function LoadingState({ label = "正在读取研究数据" }: { label?: string }) {
  return (
    <div className="loading-state">
      <div className="loading-state__line" />
      <LoaderCircle className="spin" size={18} />
      <span>{label}</span>
    </div>
  );
}

export function Modal({
  open,
  onClose,
  title,
  subtitle,
  children,
  footer
}: PropsWithChildren<{
  open: boolean;
  onClose: () => void;
  title: string;
  subtitle?: string;
  footer?: ReactNode;
}>) {
  const dialogRef = useRef<HTMLElement>(null);
  const closeRef = useRef(onClose);
  const titleId = useId();
  closeRef.current = onClose;

  useEffect(() => {
    if (!open) return;
    const previousFocus = document.activeElement as HTMLElement | null;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const dialog = dialogRef.current;
    const focusableSelector =
      'button:not([disabled]), input:not([disabled]), textarea:not([disabled]), select:not([disabled]), a[href], [tabindex]:not([tabindex="-1"])';
    window.setTimeout(() => {
      const preferred = dialog?.querySelector<HTMLElement>("[data-autofocus]");
      const first = dialog?.querySelector<HTMLElement>(focusableSelector);
      (preferred ?? first ?? dialog)?.focus();
    }, 0);

    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        event.preventDefault();
        closeRef.current();
        return;
      }
      if (event.key !== "Tab" || !dialog) return;
      const focusable = Array.from(
        dialog.querySelectorAll<HTMLElement>(focusableSelector)
      );
      if (focusable.length === 0) {
        event.preventDefault();
        dialog.focus();
        return;
      }
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    }

    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("keydown", handleKeyDown);
      document.body.style.overflow = previousOverflow;
      previousFocus?.focus();
    };
  }, [open]);

  if (!open) return null;
  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={onClose}>
      <section
        ref={dialogRef}
        className="modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        tabIndex={-1}
        onMouseDown={(event) => event.stopPropagation()}
      >
        <header className="modal__header">
          <div>
            <h2 id={titleId}>{title}</h2>
            {subtitle && <p>{subtitle}</p>}
          </div>
          <button className="icon-button" onClick={onClose} aria-label="关闭">
            <X size={18} />
          </button>
        </header>
        <div className="modal__body">{children}</div>
        {footer && <footer className="modal__footer">{footer}</footer>}
      </section>
    </div>
  );
}

export function Meter({
  value,
  label,
  tone = "green"
}: {
  value: number;
  label?: string;
  tone?: "green" | "blue" | "orange";
}) {
  const bounded = Math.max(0, Math.min(1, value || 0));
  return (
    <div className={`meter meter--${tone}`}>
      <div className="meter__track">
        <span style={{ width: `${bounded * 100}%` }} />
      </div>
      {label && <small>{label}</small>}
    </div>
  );
}

export function Stat({
  value,
  label,
  hint
}: {
  value: string | number;
  label: string;
  hint?: string;
}) {
  return (
    <div className="stat">
      <strong>{value}</strong>
      <span>{label}</span>
      {hint && <small>{hint}</small>}
    </div>
  );
}
