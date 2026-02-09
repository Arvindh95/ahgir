import { Html, Head, Main, NextScript } from 'next/document'

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

export default function Document() {
  return (
    <Html lang="en">
      <Head>
        <title>PicUr</title>
      </Head>
      <body>
        <Main />
        <NextScript />
        <script dangerouslySetInnerHTML={{ __html: TITLE_SCRIPT }} />
      </body>
    </Html>
  )
}
