import { AlertTriangle } from "lucide-react";
import { useEffect, useState } from "react";
import { Button, ErrorState, Modal } from "./Ui";

export function ConfirmDeleteModal({
  open,
  title,
  description,
  expected,
  label = "输入以下内容以确认",
  pending = false,
  error,
  onClose,
  onConfirm
}: {
  open: boolean;
  title: string;
  description: string;
  expected: string;
  label?: string;
  pending?: boolean;
  error?: unknown;
  onClose: () => void;
  onConfirm: () => void;
}) {
  const [confirmation, setConfirmation] = useState("");

  useEffect(() => {
    if (open) setConfirmation("");
  }, [open, expected]);

  return (
    <Modal
      open={open}
      onClose={pending ? () => undefined : onClose}
      title={title}
      subtitle="这项操作无法撤销。"
      footer={
        <>
          <Button variant="quiet" disabled={pending} onClick={onClose}>
            取消
          </Button>
          <Button
            variant="danger"
            loading={pending}
            disabled={confirmation !== expected}
            onClick={onConfirm}
          >
            确认删除
          </Button>
        </>
      }
    >
      <div className="delete-project-confirmation">
        <div className="destructive-summary">
          <AlertTriangle size={20} />
          <div>
            <strong>{title}</strong>
            <p>{description}</p>
          </div>
        </div>
        <label>
          <span>
            {label} <strong>{expected}</strong>
          </span>
          <input
            data-autofocus
            autoComplete="off"
            value={confirmation}
            onChange={(event) => setConfirmation(event.target.value)}
          />
        </label>
        {error !== undefined && error !== null && <ErrorState error={error} />}
      </div>
    </Modal>
  );
}
