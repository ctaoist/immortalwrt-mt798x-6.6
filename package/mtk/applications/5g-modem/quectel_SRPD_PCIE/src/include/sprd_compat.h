/* SPDX-License-Identifier: GPL-2.0 */
#ifndef _SPRD_COMPAT_H_
#define _SPRD_COMPAT_H_

#include <linux/sched.h>
#include <linux/version.h>
#if LINUX_VERSION_CODE >= KERNEL_VERSION(4, 11, 0)
#include <uapi/linux/sched/types.h>
#endif

/* Preserve the policy and priority of driver-owned kernel threads. */
static inline int sprd_sched_setscheduler(struct task_struct *task, int policy,
					 const struct sched_param *param)
{
#if LINUX_VERSION_CODE >= KERNEL_VERSION(5, 9, 0)
	const struct sched_attr attr = {
		.size = sizeof(attr),
		.sched_policy = policy,
		.sched_priority = param->sched_priority,
	};

	return sched_setattr_nocheck(task, &attr);
#else
	return sched_setscheduler(task, policy, param);
#endif
}

#endif /* _SPRD_COMPAT_H_ */
