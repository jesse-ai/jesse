/*---------------------------------------------------------------------------------------------
 *  Copyright (c) Microsoft Corporation. All rights reserved.
 *  Licensed under the MIT License. See License.txt in the project root for license information.
 *--------------------------------------------------------------------------------------------*/
import { localize } from '../../../../nls.js';
import { HoverVerbosityAction } from '../../../common/languages.js';
import { DECREASE_HOVER_VERBOSITY_ACTION_ID, INCREASE_HOVER_VERBOSITY_ACTION_ID } from './hoverActionIds.js';
import { Disposable } from '../../../../base/common/lifecycle.js';
var HoverAccessibilityHelpNLS;
(function (HoverAccessibilityHelpNLS) {
    HoverAccessibilityHelpNLS.intro = localize('intro', "Focus on the hover widget to cycle through the hover parts with the Tab key.");
    HoverAccessibilityHelpNLS.increaseVerbosity = localize('increaseVerbosity', "- The focused hover part verbosity level can be increased with the Increase Hover Verbosity command<keybinding:{0}>.", INCREASE_HOVER_VERBOSITY_ACTION_ID);
    HoverAccessibilityHelpNLS.decreaseVerbosity = localize('decreaseVerbosity', "- The focused hover part verbosity level can be decreased with the Decrease Hover Verbosity command<keybinding:{0}>.", DECREASE_HOVER_VERBOSITY_ACTION_ID);
    HoverAccessibilityHelpNLS.hoverContent = localize('contentHover', "The last focused hover content is the following.");
})(HoverAccessibilityHelpNLS || (HoverAccessibilityHelpNLS = {}));
export class HoverAccessibleView {
    dispose() {
        var _a;
        (_a = this._provider) === null || _a === void 0 ? void 0 : _a.dispose();
    }
}
export class HoverAccessibilityHelp {
    dispose() {
        var _a;
        (_a = this._provider) === null || _a === void 0 ? void 0 : _a.dispose();
    }
}
class BaseHoverAccessibleViewProvider extends Disposable {
    constructor(_hoverController) {
        super();
        this._hoverController = _hoverController;
        this._markdownHoverFocusedIndex = -1;
    }
}
export class HoverAccessibilityHelpProvider extends BaseHoverAccessibleViewProvider {
    constructor(hoverController) {
        super(hoverController);
        this.options = { type: "help" /* AccessibleViewType.Help */ };
    }
    provideContentAtIndex(index) {
        const content = [];
        content.push(HoverAccessibilityHelpNLS.intro);
        content.push(...this._descriptionsOfVerbosityActionsForIndex(index));
        content.push(...this._descriptionOfFocusedMarkdownHoverAtIndex(index));
        return content.join('\n');
    }
    _descriptionsOfVerbosityActionsForIndex(index) {
        const content = [];
        const descriptionForIncreaseAction = this._descriptionOfVerbosityActionForIndex(HoverVerbosityAction.Increase, index);
        if (descriptionForIncreaseAction !== undefined) {
            content.push(descriptionForIncreaseAction);
        }
        const descriptionForDecreaseAction = this._descriptionOfVerbosityActionForIndex(HoverVerbosityAction.Decrease, index);
        if (descriptionForDecreaseAction !== undefined) {
            content.push(descriptionForDecreaseAction);
        }
        return content;
    }
    _descriptionOfVerbosityActionForIndex(action, index) {
        const isActionSupported = this._hoverController.doesMarkdownHoverAtIndexSupportVerbosityAction(index, action);
        if (!isActionSupported) {
            return;
        }
        switch (action) {
            case HoverVerbosityAction.Increase:
                return HoverAccessibilityHelpNLS.increaseVerbosity;
            case HoverVerbosityAction.Decrease:
                return HoverAccessibilityHelpNLS.decreaseVerbosity;
        }
    }
    _descriptionOfFocusedMarkdownHoverAtIndex(index) {
        const content = [];
        const hoverContent = this._hoverController.markdownHoverContentAtIndex(index);
        if (hoverContent) {
            content.push('\n' + HoverAccessibilityHelpNLS.hoverContent);
            content.push('\n' + hoverContent);
        }
        return content;
    }
}
export class HoverAccessibleViewProvider extends BaseHoverAccessibleViewProvider {
    constructor(_keybindingService, _editor, hoverController) {
        super(hoverController);
        this._keybindingService = _keybindingService;
        this._editor = _editor;
        this.options = { type: "view" /* AccessibleViewType.View */ };
        this._initializeOptions(this._editor, hoverController);
    }
    _initializeOptions(editor, hoverController) {
        var _a;
        const helpProvider = this._register(new HoverAccessibilityHelpProvider(hoverController));
        this.options.language = (_a = editor.getModel()) === null || _a === void 0 ? void 0 : _a.getLanguageId();
        this.options.customHelp = () => { return helpProvider.provideContentAtIndex(this._markdownHoverFocusedIndex); };
    }
}
export class ExtHoverAccessibleView {
    dispose() { }
}
