# 6v6 edu command logging → /var/log/6v6-cmd.log  (tubewar 학생 활동 모니터링)
# 설치: sudo cp 6v6-cmdlog.sh /etc/profile.d/6v6-cmdlog.sh; ~/.bashrc 에 source 1줄.
# /var/log/6v6-cmd.log 는 world-writable(rw-rw-rw-) 이어야 함. 형식: <ISO_ts>\t<user>\t<cmd>
__6v6_cmdlog() {
  local ec=$?
  local last
  last=$(HISTTIMEFORMAT='' history 1 2>/dev/null | sed 's/^ *[0-9][0-9]* *//')
  [ -n "$last" ] && [ "$last" != "$__6v6_last_cmd" ] && {
    printf '%s\t%s\t%s\n' "$(date -Iseconds)" "${USER:-$(id -un)}" "$last" >> /var/log/6v6-cmd.log 2>/dev/null
    __6v6_last_cmd="$last"
  }
  return $ec
}
export HISTFILE=$HOME/.bash_history HISTSIZE=10000
case "$PROMPT_COMMAND" in *__6v6_cmdlog*) ;; *) export PROMPT_COMMAND="__6v6_cmdlog; ${PROMPT_COMMAND}";; esac
