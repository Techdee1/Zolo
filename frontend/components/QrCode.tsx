import { encode } from "uqr";

/**
 * A QR code for the customer's camera. It is a picture of the same request the 4-digit code
 * opens, so it is hidden from screen readers: they get the code, digit by digit, instead.
 * Always dark on a white square (a code on a dark page does not scan), with a quiet margin.
 */
export function QrCode({ value, size = 192 }: { value: string; size?: number }) {
  const { data } = encode(value, { ecc: "M", border: 2 });
  const n = data.length;
  const cells: string[] = [];
  data.forEach((row, y) =>
    row.forEach((on, x) => {
      if (on) cells.push(`M${x} ${y}h1v1h-1z`);
    }),
  );
  return (
    <svg
      aria-hidden="true"
      focusable="false"
      viewBox={`0 0 ${n} ${n}`}
      width={size}
      height={size}
      shapeRendering="crispEdges"
      className="rounded-zolo-control bg-white"
    >
      <path d={cells.join("")} fill="#000" />
    </svg>
  );
}
