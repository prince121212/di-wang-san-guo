const PLATFORM_DISPLAY_NAMES: Record<string, string> = {
  sglm: "热血三国联盟",
  downjoy: "当乐帝王三国",
};

export function platformDisplayName(platformKey: unknown): string {
  const key = String(platformKey ?? "").trim();
  return PLATFORM_DISPLAY_NAMES[key] ?? key;
}
