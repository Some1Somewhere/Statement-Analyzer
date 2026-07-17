const usd = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
});

export const fmtUSD = (n: number): string => usd.format(n);

export const fmtDate = (iso: string): string => {
  const d = new Date(`${iso}T00:00:00`);
  return Number.isNaN(d.getTime())
    ? iso
    : d.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
};

export const MONTH_NAMES = [
  "January", "February", "March", "April", "May", "June", "July",
  "August", "September", "October", "November", "December",
];
