/**
 * Text with an amount in it, written two ways: digits for the eye ("Approve ₦15,000") and words for
 * the ear ("Approve fifteen thousand naira to Bisi Ventures"). Both come from the message files,
 * so each language orders its own sentence; the screen reader hears only the words.
 */
export function SaidText({ visible, spoken }: { visible: string; spoken: string }) {
  return (
    <>
      <span aria-hidden="true">{visible}</span>
      <span className="sr-only">{spoken}</span>
    </>
  );
}
