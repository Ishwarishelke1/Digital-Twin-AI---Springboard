import Button from "./ui/Button";
import Modal from "./ui/Modal";

/**
 * ConfirmDialog — reusable in-app replacement for window.confirm().
 * Built on the shared Modal base, which supplies the focus trap, Escape-to-close,
 * and focus-return behavior every overlay in the app needs.
 */
function ConfirmDialog({ open, title, message, confirmLabel = "Confirm", cancelLabel = "Cancel", danger = false, onConfirm, onCancel }) {
  return (
    <Modal open={open} onClose={onCancel} title={title} maxWidth="max-w-sm">
      <p className="mb-5 text-sm text-slate-500 dark:text-slate-400">{message}</p>

      <div className="flex justify-end gap-2.5">
        <Button type="button" variant="secondary" onClick={onCancel}>
          {cancelLabel}
        </Button>

        <Button type="button" variant={danger ? "danger" : "primary"} onClick={onConfirm}>
          {confirmLabel}
        </Button>
      </div>
    </Modal>
  );
}

export default ConfirmDialog;
