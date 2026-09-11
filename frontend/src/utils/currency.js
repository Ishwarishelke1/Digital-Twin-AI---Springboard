const CURRENCY_SYMBOLS = {
  USD: "$",
  EUR: "€",
  GBP: "£",
  INR: "₹",
};

/** Returns just the symbol for a currency code, falling back to the code itself if unknown. */
export function getCurrencySymbol(currencyCode) {
  return CURRENCY_SYMBOLS[currencyCode] ?? `${currencyCode ?? ""} `;
}

/** Formats an amount with the symbol for the given currency code, falling back to the code itself if unknown. */
export function formatCurrency(amount, currencyCode) {
  return `${getCurrencySymbol(currencyCode)}${Number(amount).toLocaleString()}`;
}
