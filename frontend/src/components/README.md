# Reusable UI Components

This directory contains reusable UI components for consistent user interactions across the application.

## LoadingOverlay

A full-screen loading overlay with a spinning wheel that appears on top of all content.

### Usage

```jsx
import LoadingOverlay from './LoadingOverlay';

function MyComponent() {
  const [loading, setLoading] = useState(false);

  const handleProcess = async () => {
    setLoading(true);
    try {
      await someAsyncOperation();
    } finally {
      setLoading(false);
    }
  };

  return (
    <>
      <LoadingOverlay
        isOpen={loading}
        message="Processing data...\nThis may take a moment."
      />

      <button onClick={handleProcess}>Start Process</button>
    </>
  );
}
```

### Props

- `isOpen` (boolean): Controls overlay visibility
- `message` (string, default: 'Processing...'): Message to display (supports `\n` for multi-line)

### Features

- Full-screen semi-transparent dark backdrop (z-index: 9999)
- White content box with spinning blue loader
- Smooth fade-in and scale-up animations
- Multi-line message support
- Blocks all user interaction while visible

## ConfirmDialog

A customizable confirmation dialog that replaces `window.confirm()`.

### Usage

```jsx
import ConfirmDialog from './ConfirmDialog';

function MyComponent() {
  const [showConfirm, setShowConfirm] = useState(false);

  const handleDelete = () => {
    setShowConfirm(true);
  };

  const confirmDelete = () => {
    setShowConfirm(false);
    // Perform the delete action
  };

  return (
    <>
      <ConfirmDialog
        isOpen={showConfirm}
        title="Confirm Delete"
        message="Are you sure you want to delete this item?"
        confirmText="Delete"
        cancelText="Cancel"
        variant="danger"  // 'default', 'danger', 'warning'
        onConfirm={confirmDelete}
        onCancel={() => setShowConfirm(false)}
      />

      <button onClick={handleDelete}>Delete Item</button>
    </>
  );
}
```

### Props

- `isOpen` (boolean): Controls dialog visibility
- `title` (string): Dialog title
- `message` (string): Dialog message/question
- `confirmText` (string, default: 'Confirm'): Text for confirm button
- `cancelText` (string, default: 'Cancel'): Text for cancel button
- `variant` (string, default: 'default'): Style variant ('default', 'danger', 'warning')
- `onConfirm` (function): Callback when confirmed
- `onCancel` (function): Callback when cancelled

## Toast

A notification component that replaces `alert()` with auto-dismiss functionality.

### Usage

```jsx
import Toast from './Toast';

function MyComponent() {
  const [toast, setToast] = useState({ isOpen: false, message: '', variant: 'success' });

  const handleSuccess = () => {
    setToast({
      isOpen: true,
      message: 'Operation completed successfully!',
      variant: 'success'
    });
  };

  const handleError = () => {
    setToast({
      isOpen: true,
      message: 'An error occurred',
      variant: 'error'
    });
  };

  return (
    <>
      <Toast
        isOpen={toast.isOpen}
        message={toast.message}
        variant={toast.variant}
        duration={4000}  // Auto-dismiss after 4 seconds
        onClose={() => setToast({ ...toast, isOpen: false })}
      />

      <button onClick={handleSuccess}>Success</button>
      <button onClick={handleError}>Error</button>
    </>
  );
}
```

### Props

- `isOpen` (boolean): Controls toast visibility
- `message` (string): Toast message
- `variant` (string, default: 'success'): Style variant ('success', 'error', 'warning', 'info')
- `duration` (number, default: 4000): Auto-dismiss duration in milliseconds (0 to disable)
- `onClose` (function): Callback when closed

## Migration from window.confirm() and alert()

### Before

```jsx
const handleDelete = async () => {
  const confirmed = window.confirm('Are you sure?');
  if (!confirmed) return;

  try {
    await deleteItem();
    alert('Item deleted successfully');
  } catch (err) {
    alert(`Error: ${err.message}`);
  }
};
```

### After

```jsx
const [showConfirm, setShowConfirm] = useState(false);
const [toast, setToast] = useState({ isOpen: false, message: '', variant: 'success' });

const handleDelete = () => {
  setShowConfirm(true);
};

const confirmDelete = async () => {
  setShowConfirm(false);

  try {
    await deleteItem();
    setToast({
      isOpen: true,
      message: 'Item deleted successfully',
      variant: 'success'
    });
  } catch (err) {
    setToast({
      isOpen: true,
      message: `Error: ${err.message}`,
      variant: 'error'
    });
  }
};

return (
  <>
    <ConfirmDialog
      isOpen={showConfirm}
      title="Confirm Delete"
      message="Are you sure?"
      onConfirm={confirmDelete}
      onCancel={() => setShowConfirm(false)}
      variant="danger"
    />

    <Toast
      isOpen={toast.isOpen}
      message={toast.message}
      variant={toast.variant}
      onClose={() => setToast({ ...toast, isOpen: false })}
    />

    <button onClick={handleDelete}>Delete</button>
  </>
);
```

## Benefits

1. **Consistent UI**: Matches your application's design theme
2. **Better UX**: Smooth animations and transitions
3. **More Control**: Customizable text, styles, and behavior
4. **Accessible**: Proper keyboard navigation and ARIA attributes
5. **Non-blocking**: Toast notifications don't block user interaction
