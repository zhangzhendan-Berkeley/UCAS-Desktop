/** Require an explicit location field; titles and speaker affiliations are not venues. */
export function isYanqiLocation(location: string | null | undefined): boolean {
  const value = (location ?? "").normalize("NFKC").replace(/\s+/g, "");
  return value.includes("雁栖湖") && !/中关村|玉泉路|怀柔以外|线上|在线|网络|待定|另行通知/.test(value);
}
