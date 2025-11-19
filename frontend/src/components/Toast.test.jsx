/**
 * Tests for Toast component
 */
import { render, screen, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import Toast from './Toast';

// Mock the CSS import
vi.mock('./Toast.css', () => ({}));

describe('Toast', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('renders nothing when isOpen is false', () => {
    const { container } = render(
      <Toast isOpen={false} message="Test message" onClose={vi.fn()} />
    );

    expect(container.firstChild).toBeNull();
  });

  it('renders toast when isOpen is true', () => {
    render(
      <Toast isOpen={true} message="Test message" onClose={vi.fn()} />
    );

    expect(screen.getByText('Test message')).toBeInTheDocument();
  });

  it('renders success variant with checkmark icon', () => {
    render(
      <Toast
        isOpen={true}
        message="Success!"
        variant="success"
        onClose={vi.fn()}
      />
    );

    expect(screen.getByText('✓')).toBeInTheDocument();
  });

  it('renders error variant with X icon', () => {
    render(
      <Toast
        isOpen={true}
        message="Error!"
        variant="error"
        onClose={vi.fn()}
      />
    );

    expect(screen.getByText('✕')).toBeInTheDocument();
  });

  it('renders warning variant with warning icon', () => {
    render(
      <Toast
        isOpen={true}
        message="Warning!"
        variant="warning"
        onClose={vi.fn()}
      />
    );

    expect(screen.getByText('⚠')).toBeInTheDocument();
  });

  it('renders info variant with info icon', () => {
    render(
      <Toast
        isOpen={true}
        message="Info!"
        variant="info"
        onClose={vi.fn()}
      />
    );

    expect(screen.getByText('ℹ')).toBeInTheDocument();
  });

  it('applies correct CSS class for variant', () => {
    const { container } = render(
      <Toast
        isOpen={true}
        message="Test"
        variant="error"
        onClose={vi.fn()}
      />
    );

    const toast = container.querySelector('.toast');
    expect(toast).toHaveClass('toast-error');
  });

  it('calls onClose when close button is clicked', () => {
    const onClose = vi.fn();

    render(
      <Toast isOpen={true} message="Test" onClose={onClose} />
    );

    const closeButton = screen.getByLabelText('Close');
    closeButton.click();

    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('auto-closes after duration', () => {
    const onClose = vi.fn();

    render(
      <Toast
        isOpen={true}
        message="Test"
        duration={3000}
        onClose={onClose}
      />
    );

    expect(onClose).not.toHaveBeenCalled();

    // Fast-forward time
    vi.advanceTimersByTime(3000);

    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('uses default duration of 4000ms', () => {
    const onClose = vi.fn();

    render(
      <Toast isOpen={true} message="Test" onClose={onClose} />
    );

    vi.advanceTimersByTime(3999);
    expect(onClose).not.toHaveBeenCalled();

    vi.advanceTimersByTime(1);
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('does not auto-close when duration is 0', () => {
    const onClose = vi.fn();

    render(
      <Toast
        isOpen={true}
        message="Test"
        duration={0}
        onClose={onClose}
      />
    );

    vi.advanceTimersByTime(10000);

    expect(onClose).not.toHaveBeenCalled();
  });

  it('clears timeout when unmounted', () => {
    const onClose = vi.fn();

    const { unmount } = render(
      <Toast
        isOpen={true}
        message="Test"
        duration={3000}
        onClose={onClose}
      />
    );

    unmount();
    vi.advanceTimersByTime(3000);

    // Should not call onClose after unmount
    expect(onClose).not.toHaveBeenCalled();
  });

  it('clears and restarts timer when duration changes', () => {
    const onClose = vi.fn();

    const { rerender } = render(
      <Toast
        isOpen={true}
        message="Test"
        duration={3000}
        onClose={onClose}
      />
    );

    vi.advanceTimersByTime(1000);

    // Change duration - should reset timer
    rerender(
      <Toast
        isOpen={true}
        message="Test"
        duration={5000}
        onClose={onClose}
      />
    );

    // Advance by 3000ms - should not close yet (new duration is 5000ms)
    vi.advanceTimersByTime(3000);
    expect(onClose).not.toHaveBeenCalled();

    // Advance by remaining 2000ms to complete the 5000ms duration
    vi.advanceTimersByTime(2000);
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('renders close button with proper accessibility', () => {
    render(
      <Toast isOpen={true} message="Test" onClose={vi.fn()} />
    );

    const closeButton = screen.getByLabelText('Close');
    expect(closeButton).toBeInTheDocument();
    expect(closeButton).toHaveAttribute('aria-label', 'Close');
  });
});
