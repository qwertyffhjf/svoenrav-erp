// Runs the committed HTML as a local file; all assets must be self-contained.
const assert=require("node:assert/strict");
const fs=require("node:fs");
const path=require("node:path");
const {JSDOM,VirtualConsole,ResourceLoader}=require("jsdom");
const root=path.join(__dirname,"../..");
const html=fs.readFileSync(path.join(root,"SVOENRAV_PREVIEW.html"),"utf8");
const errors=[];const requests=[];
class NoNetwork extends ResourceLoader { fetch(url){requests.push(url);return null;} }
const consoleSink=new VirtualConsole();consoleSink.on("jsdomError",error=>errors.push(error));
const dom=new JSDOM(html,{url:"file:///test/SVOENRAV_PREVIEW.html",runScripts:"dangerously",resources:new NoNetwork(),virtualConsole:consoleSink,beforeParse(window){window.scrollTo=()=>{};}});
const turn=()=>new Promise(setImmediate);
(async()=>{
 try {
  await turn();await turn();
  const {window}=dom;const page=window.SVOENRAV_PREVIEW_PAGE;
  assert.ok(page?.ready,errors.map(e=>e.message).join("\n"));
  assert.match(window.document.querySelector(".preview-banner").textContent,/ВСЕ ДАННЫЕ ТЕСТОВЫЕ/);
  assert.equal(window.document.querySelectorAll(".sv-action").length,17);
  assert.match(window.document.getElementById("preview-source-hash").textContent,/^[a-f0-9]{64}$/);
  assert.match(html,/connect-src 'none'/);
  for(const test of window.SVOENRAV_DEMO.cutting_cases){
   if(test.valid){
    const result=window.SVOENRAV_PREVIEW_CALCULATE_CUTTING(test.input);
    assert.deepEqual(JSON.parse(JSON.stringify(result)),JSON.parse(JSON.stringify(test.result)));
   } else assert.throws(()=>window.SVOENRAV_PREVIEW_CALCULATE_CUTTING(test.input));
  }
  window.document.getElementById("preview-example-button").click();await turn();
  assert.equal(page.cutting_fields.input_area.get_value(),"20");
  page.cutting_button[0].click();await turn();
  assert.match(page.cutting_review.text(),/Баланс сходится/);
  assert.equal(window.document.getElementById("preview-document").hidden,true);
  page.cutting_review_controls.checkbox.prop("checked",true).trigger("change");
  page.cutting_review_controls.open[0].click();await turn();
  assert.equal(window.document.getElementById("preview-document").hidden,false);
  assert.match(window.document.getElementById("preview-document-body").textContent,/Сохранение и проведение отключены/);
  window.document.getElementById("preview-home-button").click();
  window.document.querySelector("a[href$='?view=cutting']").click();await turn();
  assert.equal(window.document.getElementById("preview-workshop").hidden,false);
  await page.cutting_fields.waste_area.set_value("3");
  page.cutting_button[0].click();await turn();
  assert.match(page.cutting_review.text(),/Раскрой не подтверждён/);
  assert.match(window.document.getElementById("preview-message").textContent,/Баланс не сходится/);

  window.document.getElementById("preview-order-button").click();await turn();await turn();
  assert.match(page.card.text(),/Работа по заказу/);
  assert.match(page.card.text(),/DEMO-PAY-001/);
  assert.match(page.card.text(),/DEMO-INV-001/);
  await page.load_history(window.SVOENRAV_DEMO.sales_order.name);
  assert.match(page.history_body.text(),/Not Started/);
  await page.open_operation("delivery",window.SVOENRAV_DEMO.sales_order.name);
  await page.prepare();
  assert.match(page.operation_review.text(),/DEMO-DN-DRAFT/);
  assert.equal(page.operation_review_controls,null);
  page.show("plan");await page.load_plan();
  assert.match(page.plan_body.text(),/DEMO-WO-002/);
  assert.match(page.plan_body.text(),/Дефицит/);
  assert.equal(window.SVOENRAV_DEMO.plan.orders[1].rows[0].planned_free,0);
  assert.equal(window.SVOENRAV_DEMO.plan.orders[1].rows[0].shortage,20);
  page.open_materials(window.SVOENRAV_DEMO.work_order.name);await turn();
  await page.load_specification();
  assert.match(page.spec_body.text(),/ещё не зафиксирован/);
  page.spec_body.find("button")[0].click();await turn();
  assert.match(page.spec_body.text(),/совпадают со снимком/);
  page.simple_button[0].click();
  assert.ok(page.root.hasClass("sv-simple"));
  await assert.rejects(window.fetch("https://example.com"));
  assert.deepEqual(requests,[]);
  assert.deepEqual(errors.map(e=>e.message),[]);
  console.log("Standalone HTML: real template/JS, local file navigation, cutting parity, review gate and no network OK");
 } finally {dom.window.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
