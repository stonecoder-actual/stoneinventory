const $ = (selector) => document.querySelector(selector);
const fields = ['name','brand','package_size','category','ingredients','allergens','dietary_labels','serving_size','servings_per_package','minimum_quantity','target_quantity'];
const nutrientFields = ['calories_kcal','protein_g','carbohydrates_g','fat_g','fiber_g','sugars_g','sodium_mg'];
let products = [], view = 'all', current = null, countProduct = null, review = false, pending = null, opening = false;
function requestId() {
  if (typeof crypto.randomUUID === 'function') return crypto.randomUUID();
  // getRandomValues also works on plain HTTP within a trusted LAN.
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  bytes[6] = (bytes[6] & 15) | 64; bytes[8] = (bytes[8] & 63) | 128;
  const hex = [...bytes].map(value => value.toString(16).padStart(2,'0')).join('');
  return [hex.slice(0,8),hex.slice(8,12),hex.slice(12,16),hex.slice(16,20),hex.slice(20)].join('-');
}
const low = p => p.quantity <= p.minimum_quantity;
const label = p => p.name || 'Unidentified product';
function node(tag, attrs = {}, ...children) {
  const element = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (key === 'class') element.className = value;
    else if (key.startsWith('on')) element.addEventListener(key.slice(2), value);
    else element.setAttribute(key, value);
  }
  for (const child of children.flat()) if (child !== null && child !== undefined) element.append(child);
  return element;
}
function notify(text, error = false) {
  $('#message').textContent = text; $('#message').classList.toggle('error', error); $('#message').hidden = false;
}
async function api(path, options = {}) {
  const response = await fetch(path, { ...options, headers: { 'Content-Type': 'application/json', ...options.headers }, signal: AbortSignal.timeout(15000) });
  let result;
  try { result = await response.json(); } catch { throw new Error('The server returned an unreadable reply.'); }
  if (!response.ok) {
    const error = new Error(typeof result.detail === 'string' ? result.detail : 'Please check the entered values and try again.');
    error.status = response.status; throw error;
  }
  return result;
}
function render() {
  const counts = { all: products.length, low: products.filter(low).length, unknown: products.filter(p => p.unresolved).length };
  for (const key of Object.keys(counts)) { $('#nav-' + key).textContent = counts[key]; $('#stat-' + key).textContent = counts[key]; }
  document.querySelectorAll('[data-view]').forEach(button => {
    const active = button.dataset.view === view;
    button.classList.toggle('active', active); button.classList.toggle('selected', active);
    button.setAttribute('aria-pressed', String(active));
  });
  const titles = {
    all: ['Know what’s at home.', 'Your pantry, cupboards, and everyday essentials, all in one place.', 'The household shelf', 'INVENTORY'],
    low: ['A little list. A stocked home.', 'Everything at or below its minimum count, ready for your next shop.', 'Your shopping list', 'SHOPPING LIST'],
    unknown: ['Every barcode deserves a name.', 'Identify these products once. Their counts and history stay right where they are.', 'Waiting to be identified', 'NEEDS A NAME']
  }[view];
  ['#page-title','#page-description','#section-title','#breadcrumb'].forEach((selector, i) => $(selector).textContent = titles[i]);
  $('#last-column').textContent = view === 'low' ? 'TO BUY / DETAILS' : 'DETAILS';
  const query = $('#search').value.trim().toLocaleLowerCase();
  let visible = products.filter(p => (view === 'all' || (view === 'low' ? low(p) : p.unresolved)) &&
    [p.name,p.brand,p.barcode,p.category].filter(Boolean).join(' ').toLocaleLowerCase().includes(query));
  visible.sort((a,b) => $('#sort').value === 'quantity' ? a.quantity - b.quantity : $('#sort').value === 'updated' ? b.updated_at.localeCompare(a.updated_at) : label(a).localeCompare(label(b)));
  $('#result-count').textContent = visible.length + (visible.length === 1 ? ' product' : ' products') + (query ? ' matching your search' : ' in this view');
  $('#rows').replaceChildren(...visible.map(p => {
    const status = p.unresolved ? ['unknown','Needs a name'] : low(p) ? ['low','Low stock'] : ['stock','In stock'];
    const initials = p.name ? p.name.trim().slice(0,2).toUpperCase() : '?';
    return node('tr', {}, node('td', {}, node('div', {class:'product-cell'}, node('span', {class:'product-icon', 'aria-hidden':'true'}, initials),
      node('div', {}, node('button', {class:'product-link', onclick:() => showDetail(p.barcode)}, label(p)),
        node('span', {class:'product-meta'}, ([p.brand,p.package_size].filter(Boolean).join(' · ') || p.barcode) + (view === 'low' ? ' · To buy: ' + Math.max(0,p.target_quantity-p.quantity) : ''))))),
      node('td', {}, node('strong', {class:'quantity'}, String(p.quantity)), node('small', {class:'count-unit'}, p.quantity === 1 ? 'package' : 'packages')),
      node('td', {}, node('span', {class:'badge '+status[0]}, status[1])),
      node('td', {class:'row-action'}, ...(view === 'low' ? [node('span', {class:'buy-count'}, 'Buy ' + Math.max(0,p.target_quantity-p.quantity))] : []),
        node('button', {class:'secondary small', onclick:() => showDetail(p.barcode)}, p.unresolved ? 'Identify' : 'View →')));
  }));
  $('#inventory-table').hidden = !visible.length; $('#empty').hidden = !!visible.length;
  $('#empty-title').textContent = query ? 'No matching products' : view === 'unknown' ? 'Everything has a name.' : view === 'low' ? 'You’re looking well stocked.' : 'Your shelf starts here.';
  $('#empty-description').textContent = query ? 'Try another name, brand, or barcode.' : view === 'unknown' ? 'New unknown barcodes will appear here for you to identify.' : view === 'low' ? 'Products appear here when their count reaches the minimum you set.' : 'Add a product to start, or scan an item at your inventory terminal when connected.';
}
async function refresh() {
  $('#refresh').disabled = true;
  try { products = await api('/api/products'); render(); }
  catch (error) { notify('Could not refresh inventory. ' + error.message, true); }
  finally { $('#refresh').disabled = false; }
}
function dl(items) {
  return node('dl', {class:'details-list'}, items.flatMap(([term,value]) => [node('dt',{},term),node('dd',{},value ?? 'Not recorded')]));
}
async function showDetail(barcode) {
  if (opening) return;
  opening = true;
  try {
    const [product, history] = await Promise.all([api('/api/products/'+barcode),api('/api/products/'+barcode+'/transactions')]);
    current = product;
    const nutrition = product.nutrition || {};
    const basisLabels = {per_serving:'Per serving',per_100g:'Per 100 g',per_100ml:'Per 100 ml',per_100g_or_100ml:'Per 100 g or 100 ml — source unclear'};
    const content = [
      node('h2',{id:'detail-title'},label(product)),node('p',{class:'muted'},[product.brand,product.package_size].filter(Boolean).join(' · ') || product.barcode),
      node('div',{class:'detail-count'},node('strong',{},String(product.quantity)),node('span',{},'packages on hand')),
      node('div',{class:'detail-buttons'},node('button',{class:'primary',onclick:() => openEditor(product)},product.unresolved ? 'Identify product' : 'Edit product'),
        node('button',{class:'secondary',onclick:() => openCount(product)},'Correct count')),
      dl([['Barcode',product.barcode],['Category',product.category],['Minimum / target',product.minimum_quantity+' / '+product.target_quantity],
        ['Source',product.manually_verified ? 'Manually verified' : product.source === 'openfoodfacts' ? 'Open Food Facts · not manually verified' : 'Unidentified']]),
      node('h3',{},'Nutrition & ingredients'),
      node('p',{class:'hint'},basisLabels[nutrition.basis] || 'Nutrition not recorded.'),
      dl([['Calories',nutrition.calories_kcal == null ? null : nutrition.calories_kcal+' kcal'],['Protein',nutrition.protein_g == null ? null : nutrition.protein_g+' g'],
        ['Carbohydrates',nutrition.carbohydrates_g == null ? null : nutrition.carbohydrates_g+' g'],['Fat',nutrition.fat_g == null ? null : nutrition.fat_g+' g'],
        ['Fiber',nutrition.fiber_g == null ? null : nutrition.fiber_g+' g'],['Sugars',nutrition.sugars_g == null ? null : nutrition.sugars_g+' g'],['Sodium',nutrition.sodium_mg == null ? null : nutrition.sodium_mg+' mg'],['Serving size',product.serving_size],['Servings per package',product.servings_per_package == null ? null : String(product.servings_per_package)],
        ['Ingredients',product.ingredients],['Allergens',product.allergens],['Dietary labels',product.dietary_labels]]),
      node('h3',{},'Inventory history'),node('p',{class:'hint'},'Corrections are kept separate from items added and removed.')
    ];
    const events = node('ol',{class:'history'});
    for (const event of [...history].reverse()) {
      events.append(node('li',{},node('div',{},node('strong',{}, {ADD:'Added',REMOVE:'Removed',RECONCILE:'Count corrected'}[event.action] || event.action),
        node('small',{},new Date(event.timestamp).toLocaleString()+' · '+event.device_id)),
        node('span',{},event.quantity_before+' → '+event.quantity_after)));
    }
    content.push(history.length ? events : node('p',{class:'muted'},'No inventory changes yet.'));
    $('#detail-content').replaceChildren(...content); $('#detail-dialog').showModal();
  } catch (error) { notify(error.message,true); }
  finally { opening = false; }
}
function openEditor(product = null) {
  $('#detail-dialog').close();
  const form = $('#edit-form'); form.reset(); $('#edit-error').textContent = '';
  $('#edit-title').textContent = product ? product.unresolved ? 'Identify this product' : 'Edit product information' : 'Add a product';
  form.elements.barcode.value = product?.barcode || ''; form.elements.barcode.readOnly = !!product;
  for (const field of fields) form.elements[field].value = product?.[field] ?? (field.endsWith('_quantity') ? 0 : '');
  for (const field of nutrientFields) form.elements[field].value = product?.nutrition?.[field] ?? '';
  form.elements.basis.value = product?.nutrition?.basis || '';
  $('#edit-dialog').showModal();
}
$('#edit-form').addEventListener('submit',async event => {
  event.preventDefault();
  const form = event.currentTarget, button = form.querySelector('[type=submit]');
  if (button.disabled) return;
  const payload = {};
  for (const field of fields) {
    const value = form.elements[field].value.trim();
    payload[field] = ['minimum_quantity','target_quantity','servings_per_package'].includes(field) ? value ? Number(value) : null : value || null;
  }
  const enteredNutrition = nutrientFields.some(field => form.elements[field].value !== '');
  if (enteredNutrition && !form.elements.basis.value) { $('#edit-error').textContent = 'Choose a nutrition basis for the values you entered.'; return; }
  payload.nutrition = form.elements.basis.value ? { basis:form.elements.basis.value } : null;
  if (payload.nutrition) for (const field of nutrientFields) payload.nutrition[field] = form.elements[field].value === '' ? null : Number(form.elements[field].value);
  button.disabled = true; $('#edit-error').textContent = '';
  try {
    const product = await api('/api/products/'+form.elements.barcode.value,{method:'PUT',body:JSON.stringify(payload)});
    $('#edit-dialog').close(); notify('Product saved. Its inventory count and history are unchanged.'); await refresh(); await showDetail(product.barcode);
  } catch (error) { $('#edit-error').textContent = error.message; }
  finally { button.disabled = false; }
});
function openCount(product) {
  if (pending) { notify('Retry the pending inventory change before making another correction.',true); return; }
  $('#detail-dialog').close(); countProduct = {...product}; review = false;
  $('#count-name').textContent = label(product); $('#new-count').value = product.quantity; $('#count-error').textContent = '';
  $('#count-submit').textContent = 'Review change'; updatePreview(); $('#count-dialog').showModal();
}
function updatePreview() {
  $('#count-preview').textContent = (countProduct?.quantity ?? 0)+' → '+($('#new-count').value || '—')+' packages';
}
$('#new-count').addEventListener('input',() => { review = false; $('#count-submit').textContent = 'Review change'; updatePreview(); });
function pendingUI() {
  $('#pending-box').hidden = !pending;
  if (pending) $('#pending-text').textContent = 'Set barcode '+pending.body.barcode+' to '+pending.body.quantity+' packages. A retry will not repeat the change.';
}
function savePending(value) {
  // Persist before sending so a reload or lost reply cannot turn a retry into a second operation.
  if (value) sessionStorage.setItem('stoneinventory.pending',JSON.stringify(value));
  else sessionStorage.removeItem('stoneinventory.pending');
  pending = value; pendingUI();
}
async function sendPending() {
  if (!pending || $('#retry').disabled) return;
  $('#retry').disabled = true; $('#count-submit').disabled = true;
  const operation = pending;
  try {
    const response = await api('/api/inventory/reconcile',{method:'POST',body:JSON.stringify(operation.body)});
    savePending(null); $('#count-dialog').close();
    notify('Count corrected: '+response.inventory.before+' → '+response.inventory.after+'. This was recorded as a reconciliation.');
    await refresh(); await showDetail(operation.body.barcode);
  } catch (error) {
    if (error.status && error.status < 500) {
      savePending(null); $('#count-dialog').close(); notify(error.message,true); await refresh();
    } else { $('#count-dialog').close(); notify('The result is not confirmed. Use “Retry safely” to check the same change.',true); }
  } finally { $('#retry').disabled = false; $('#count-submit').disabled = false; }
}
$('#count-form').addEventListener('submit',async event => {
  event.preventDefault(); if ($('#count-submit').disabled) return;
  if (!review) { review = true; $('#count-submit').textContent = 'Confirm correction'; return; }
  if (pending) return;
  try {
    savePending({body:{barcode:countProduct.barcode,quantity:Number($('#new-count').value),expected_quantity:countProduct.quantity,device_id:'household-web',request_id:requestId()}});
    await sendPending();
  } catch { $('#count-error').textContent = 'Your browser could not save a safe retry token. Enable session storage before correcting inventory.'; }
});
document.querySelectorAll('[data-close]').forEach(button => button.addEventListener('click',() => document.getElementById(button.dataset.close).close()));
document.querySelectorAll('[data-view]').forEach(button => button.addEventListener('click',() => { view = button.dataset.view; render(); }));
$('#search').addEventListener('input',render); $('#sort').addEventListener('change',render);
$('#refresh').addEventListener('click',refresh); $('#new-product').addEventListener('click',() => openEditor());
$('#retry').addEventListener('click',sendPending);
try { const saved = JSON.parse(sessionStorage.getItem('stoneinventory.pending') || 'null'); if (saved?.body?.request_id && /^[0-9]{8,14}$/.test(saved.body.barcode) && Number.isInteger(saved.body.quantity)) pending = saved; } catch { /* No request has been sent during this load. */ }
pendingUI(); refresh();
