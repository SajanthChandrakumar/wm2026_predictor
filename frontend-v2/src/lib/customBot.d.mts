import type { CustomBot, CustomBotParams } from './types'

export declare const DEFAULT_BOT_PARAMS: CustomBotParams
export declare function botFormState(customBot: CustomBot | undefined): { name: string; params: CustomBotParams }
