import { Html, Head, Main, NextScript } from 'next/document'

export default function Document() {
  return (
    <Html lang="en">
      <Head />
      <body>
        <Main />
        <NextScript />
        <script dangerouslySetInnerHTML={{ __html: `
          (function(){
            var meta=document.querySelector('meta[name="page-title"]');
            if(meta&&meta.content){
              document.title=meta.content;
            }else if(!document.title||document.title===location.href||document.title===location.pathname){
              document.title='PicUr';
            }
          })();
        ` }} />
      </body>
    </Html>
  )
}
