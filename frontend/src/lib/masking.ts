export function maskEmail(email: string | undefined | null): string {
  if (!email) return "";
  const parts = email.split("@");
  if (parts.length !== 2) return email;
  const [local, domain] = parts;
  if (local.length <= 2) return local[0] + "*@" + domain;
  const first = local[0];
  const last = local[local.length - 1];
  return `${first}${"*".repeat(Math.max(1, local.length - 2))}${last}@${domain}`;
}

export function maskPhone(phone: string | undefined | null): string {
  if (!phone) return "";
  // Extract digits
  const digits = phone.replace(/\D/g, "");
  if (digits.length <= 4) return "****";
  const last4 = digits.slice(-4);
  const prefix = phone.startsWith("+") ? "+" : "";
  return `${prefix}***-***-${last4}`;
}

export function maskPII(value: string | undefined | null, type: "email" | "phone") {
  return type === "email" ? maskEmail(value) : maskPhone(value);
}
