goog.provide('cms.test');

goog.require('goog.dom');

goog.require('cms.greet');

/**
 * Greets the user.
 * 
 */
cms.test.sayHello = function (name) {
    var newHeader = goog.dom.createDom('h1', {'class': goog.getCssName('cms-greeting')}, cms.greet.greetUser({'name': name}));
    goog.dom.appendChild(document.body, newHeader);
}

/**
 * Initialize.
 */
cms.test.init = function () {
    var form = goog.dom.getElement('greeter');
    form.addEventListener('submit', function (evt) {
        evt.preventDefault();
        cms.test.sayHello(goog.dom.getFirstElementChild(form).value);
        return false;
    }, false);
}

// Ensures the symbols will be visible after compiler renaming.
goog.exportSymbol('cms.test.sayHello', cms.test.sayHello);
goog.exportSymbol('cms.test.init', cms.test.init);

goog.exportSymbol('cms.greet.form', cms.greet.form);
