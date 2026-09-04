/* next/link 대체. 이 사이트는 정적 2쪽이라 라우터가 필요 없다 — 진짜 링크로 넘긴다.
   GitHub Pages 는 저장소 이름이 경로에 붙으므로(/stores-scout/), 절대 경로 앞에
   Vite 의 base 를 얹는다. 이걸 빼면 로컬에서는 되고 배포에서만 404 가 난다. */
import * as React from 'react';

const BASE = (import.meta.env.BASE_URL || '/').replace(/\/$/, '');

type Props = React.ComponentPropsWithoutRef<'a'> & { href: string };

const Link = React.forwardRef<HTMLAnchorElement, Props>(function Link(
  { href, ...rest }, ref,
) {
  const to = href.startsWith('/') ? `${BASE}${href}` : href;
  return <a ref={ref} href={to} {...rest} />;
});

export default Link;
