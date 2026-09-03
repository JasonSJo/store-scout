/** 국내 대표번호/일반전화/휴대전화 입력용 표시 형식. 숫자 최대 11자리만 보관합니다. */
export function formatKoreanPhone(input: string): string {
  const n = input.replace(/\D/g, '').slice(0, 11);
  if (!n) return '';
  if (n.startsWith('02')) {
    if (n.length <= 2) return n;
    if (n.length <= 5) return `${n.slice(0, 2)}-${n.slice(2)}`;
    if (n.length <= 9) return `${n.slice(0, 2)}-${n.slice(2, 5)}-${n.slice(5)}`;
    return `${n.slice(0, 2)}-${n.slice(2, 6)}-${n.slice(6)}`;
  }
  if (n.length <= 3) return n;
  if (n.length <= 6) return `${n.slice(0, 3)}-${n.slice(3)}`;
  if (n.length <= 10) return `${n.slice(0, 3)}-${n.slice(3, 6)}-${n.slice(6)}`;
  return `${n.slice(0, 3)}-${n.slice(3, 7)}-${n.slice(7)}`;
}
