// Real Chromium layout and interactions for the offline preview, not server acceptance.
const assert=require('node:assert/strict');
const path=require('node:path');
const {pathToFileURL}=require('node:url');
const {chromium}=require('playwright');
(async()=>{
 const browser=await chromium.launch({headless:true,args:['--no-sandbox']});
 try {
  for(const width of [320,390,1280]) {
   const page=await browser.newPage({viewport:{width,height:900}});
   const errors=[];page.on('pageerror',error=>errors.push(error.message));
   await page.goto(pathToFileURL(path.resolve(__dirname,'../../SVOENRAV_PREVIEW.html')).href);
   await page.waitForFunction(()=>window.SVOENRAV_PREVIEW_PAGE?.ready);
   const overflow=()=>page.evaluate(()=>document.documentElement.scrollWidth > innerWidth+1);
   assert.equal(await overflow(),false,`Home overflows at ${width}`);

   await page.locator("a[href$='?view=catalog']").click();
   await page.getByRole('button',{name:'Открыть модель',exact:true}).waitFor();
   assert.equal(await overflow(),false,`Catalog overflows at ${width}`);
   await page.getByRole('button',{name:'Открыть модель',exact:true}).click();
   await page.locator('.sv-gallery img').nth(1).waitFor();
   await page.waitForFunction(()=>Array.from(document.querySelectorAll('.sv-gallery img')).every(img=>img.complete && img.naturalWidth>0));
   assert.equal(await page.locator('.sv-gallery img').count(),2);
   await page.getByRole('button',{name:'На обложку',exact:true}).nth(1).click();
   await page.waitForFunction(()=>document.querySelector('.sv-model-card img')?.src===window.SVOENRAV_DEMO.models[0].photos[1].url);
   await page.screenshot({path:`/tmp/svoenrav-catalog-${width}.png`,fullPage:true});
   await page.getByRole('button',{name:'Добавить фотографии',exact:true}).click();
   assert.match(await page.locator('#preview-message').innerText(),/файлы не загружаются/);
   await page.getByRole('button',{name:'Добавить модель',exact:true}).click();
   await page.locator('input[name=code]').fill('DEMO-BROWSER-'+width);
   await page.locator('input[name=title]').fill('Новая демо-модель '+width);
   await page.locator('input[name=stock_uom]').fill('шт');
   await page.locator('input[name=item_group]').fill('Демо-изделия');
   await page.getByRole('button',{name:'Сохранить модель',exact:true}).click();
   await page.getByRole('heading',{name:'Новая демо-модель '+width,exact:true,level:2}).waitFor();
   assert.equal(await overflow(),false,`New model overflows at ${width}`);
   if(width<=600) await page.getByLabel('Раздел мастерской',{exact:true}).selectOption('units');
   else await page.getByRole('button',{name:'Номерные изделия',exact:true}).click();
   await page.getByText('000001',{exact:true}).waitFor();
   await page.getByRole('row').filter({hasText:'000001'}).getByRole('button',{name:'Открыть изделие',exact:true}).click();
   await page.getByRole('heading',{name:'SVOENRAV № 000001',exact:true}).waitFor();
   assert.match(await page.locator('.sv-catalog-detail').last().innerText(),/DEMO-MFG-001/);
   assert.equal(await overflow(),false,`Unit card overflows at ${width}`);
   await page.screenshot({path:`/tmp/svoenrav-unit-${width}.png`,fullPage:true});
   await page.locator('#preview-order-button').click();
   await page.getByRole('heading',{name:'Работа по заказу',exact:true}).waitFor();
   assert.equal(await overflow(),false,`Order overflows at ${width}`);
   await page.screenshot({path:`/tmp/svoenrav-order-${width}.png`,fullPage:true});
   if(width <= 600) await page.getByLabel('Раздел мастерской',{exact:true}).selectOption('plan');
   else await page.evaluate(()=>window.SVOENRAV_PREVIEW_PAGE.show('plan'));
   await page.getByRole('button',{name:'Рассчитать план',exact:true}).click();
   await page.getByText('DEMO-WO-002 · Дефицит',{exact:true}).waitFor();
   assert.equal(await overflow(),false,`Plan overflows at ${width}`);
   await page.screenshot({path:`/tmp/svoenrav-plan-${width}.png`,fullPage:true});
   page.once('dialog',dialog=>dialog.accept());
   await page.getByRole('button',{name:'Создать складские резервы по очереди',exact:true}).click();
   await page.getByText(/Создано резервов: 1/).waitFor();
   await page.evaluate(()=>window.SVOENRAV_PREVIEW_PAGE.open_materials('DEMO-WO-001'));
   await page.getByRole('button',{name:'Проверить зафиксированный состав',exact:true}).click();
   await page.getByText('Нормы совпадают со снимком',{exact:true}).waitFor();
   assert.equal(await overflow(),false,`Specification overflows at ${width}`);
   await page.locator('#preview-example-button').click();
   await page.getByRole('button',{name:'Проверить раскрой',exact:true}).click();
   await page.getByText(/Баланс сходится/).waitFor();
   assert.equal(await overflow(),false,`Cutting overflows at ${width}`);
   await page.getByLabel('Проверил данные подготовленного документа',{exact:true}).check();
   await page.getByRole('button',{name:'Открыть документ ERPNext',exact:true}).click();
   await page.locator('#preview-document:not([hidden])').waitFor();
   assert.equal(await overflow(),false,`Document overflows at ${width}`);
   await page.screenshot({path:`/tmp/svoenrav-preview-${width}.png`,fullPage:true});
   assert.deepEqual(errors,[],`JS errors at ${width}`);
   await page.close();
  }
  console.log('Chromium: 320/390/1280px, no page overflow, order/plan/reserve/spec/cutting/review interactions OK');
 } finally {await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
