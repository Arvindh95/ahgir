import Document, { Html, Head, Main, NextScript, DocumentContext, DocumentInitialProps } from 'next/document'

const TITLE_SCRIPT = `
(function(){
  var t={
    '/':'PicUr',
    '/admin/login':'Login - PicUr',
    '/admin/register':'Register - PicUr',
    '/admin/forgot-password':'Forgot Password - PicUr',
    '/admin/verify':'Verify Email - PicUr',
    '/admin/reset-password':'Reset Password - PicUr',
    '/admin/superadmin':'Super Admin - PicUr',
    '/admin/events':'Events - PicUr',
    '/admin/events/create':'Create Event - PicUr',
    '/privacy':'Privacy Policy - PicUr',
    '/terms':'Terms of Service - PicUr',
    '/contact':'Contact - PicUr',
    '/pricing':'Pricing - PicUr'
  };
  var p=[
    [/^\\/admin\\/events\\/[^/]+\\/photos$/,'Photos - PicUr'],
    [/^\\/admin\\/events\\/[^/]+$/,'Event Details - PicUr'],
    [/^\\/e\\/[^/]+\\/gallery$/,'Gallery - PicUr'],
    [/^\\/e\\/[^/]+\\/results$/,'Results - PicUr'],
    [/^\\/e\\/[^/]+\\/scan$/,'Scan - PicUr'],
    [/^\\/e\\/[^/]+$/,'Event - PicUr']
  ];
  function g(path){
    path=path.split('?')[0].split('#')[0];
    if(path.length>1&&path.endsWith('/'))path=path.slice(0,-1);
    if(t[path])return t[path];
    for(var i=0;i<p.length;i++){if(p[i][0].test(path))return p[i][1];}
    return 'PicUr';
  }
  function u(){document.title=g(window.location.pathname);}
  var op=history.pushState;
  var or=history.replaceState;
  history.pushState=function(){op.apply(this,arguments);setTimeout(u,0);};
  history.replaceState=function(){or.apply(this,arguments);setTimeout(u,0);};
  window.addEventListener('popstate',function(){setTimeout(u,0);});
  u();setTimeout(u,50);setTimeout(u,200);setTimeout(u,500);
})();
`;

interface PicUrDocumentProps extends DocumentInitialProps {
  nonce: string
}

class PicUrDocument extends Document<PicUrDocumentProps> {
  static async getInitialProps(ctx: DocumentContext): Promise<PicUrDocumentProps> {
    const initialProps = await Document.getInitialProps(ctx)
    // middleware.ts attaches the nonce per request; default to '' so
    // dev-server pages without middleware still render (no CSP enforced).
    const headerNonce = ctx.req?.headers?.['x-nonce']
    const nonce = typeof headerNonce === 'string' ? headerNonce : ''
    return { ...initialProps, nonce }
  }

  render() {
    const { nonce } = this.props
    return (
      <Html lang="en">
        {/* No <title> here — _app.tsx owns the per-route title. A static
            default title here would render alongside the dynamic one and
            browsers would pick the wrong one (the post-build inject-titles
            hack used to scrub it). */}
        <Head nonce={nonce} />
        <body>
          <Main />
          <NextScript nonce={nonce} />
          <script nonce={nonce} dangerouslySetInnerHTML={{ __html: TITLE_SCRIPT }} />
        </body>
      </Html>
    )
  }
}

export default PicUrDocument
